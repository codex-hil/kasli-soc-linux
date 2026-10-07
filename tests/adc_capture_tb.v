`timescale 1ns/1ps
// Functional control/RAM CDC test, not a physical LVDS or timing model.
module tb;
    reg sys_clk=0, adc_clk=0, reset=1, arm=0, ext_mode=0, trigger=0, aligned=0;
    always #5 sys_clk=~sys_clk;
    always #4.7 adc_clk=~adc_clk;
    reg [7:0] frame=8'h0f;
    reg [63:0] samples=0;
    reg [9:0] read_address=0;
    wire [63:0] read_data;
    wire done;
    wire [10:0] captured, errors;
    wire [31:0] sample_gray;
    fmc_adc_capture dut(sys_clk,adc_clk,reset,arm,ext_mode,trigger,aligned,frame,
                        samples,read_address,read_data,done,captured,errors,sample_gray);
    reg [63:0] expected [0:1023];
    integer writes=0, i;
    always @(negedge adc_clk) samples <= samples + 64'h00040008000c0010;
    always @(posedge adc_clk) if (!reset && dut.state==2) begin
        expected[writes] = samples;
        writes = writes+1;
    end
    task verify;
        begin
            if (writes != 1024 || captured != 1024) $fatal(1,"capture length mismatch");
            for (i=0;i<1024;i=i+1) begin
                @(negedge sys_clk); read_address=i;
                repeat(2) @(posedge sys_clk);
                @(negedge sys_clk);
                if (read_data !== expected[i]) $fatal(1,"snapshot sample %0d mismatch",i);
            end
            repeat(30) @(posedge adc_clk);
            if (writes != 1024) $fatal(1,"frozen buffer was overwritten");
        end
    endtask
    initial begin
        #37 reset=0;
        #21 arm=1;
        repeat(15) @(posedge adc_clk);
        if (writes != 0 || done != 0) $fatal(1,"captured without alignment");
        @(negedge adc_clk); aligned=1;
        wait(done==1);
        if(errors != 0) $fatal(1,"clean frame reported errors");
        verify;
        writes=0;
        @(negedge sys_clk); ext_mode=1;
        repeat(5) @(posedge adc_clk);
        @(negedge sys_clk); arm=0;
        repeat(20) @(posedge adc_clk);
        if(writes != 0 || done != 1) $fatal(1,"external trigger bypassed");
        @(negedge adc_clk); trigger=1;
        wait(writes==10);
        @(negedge adc_clk); frame=0; aligned=0;
        repeat(7) @(posedge adc_clk);
        @(negedge adc_clk); frame=8'h0f; aligned=1;
        wait(done==0);
        if(errors != 7) $fatal(1,"expected 7 frame errors, got %0d",errors);
        verify;
        // Abort midway and verify async control reset, then successful re-arm.
        writes=0; ext_mode=0;
        repeat(5) @(posedge adc_clk);
        arm=1;
        wait(writes==100);
        #1 reset=1; arm=0;
        #20;
        if(captured != 0 || done != 0) $fatal(1,"abort did not reset handshake");
        writes=0; reset=0;
        repeat(10) @(posedge adc_clk);
        arm=1;
        wait(done==1);
        verify;
        $display("PASS: async clocks, alignment gating, 3 snapshots, external trigger, frame errors, frozen RAM, abort/re-arm");
        $finish;
    end
    initial begin #1000000; $fatal(1,"capture timeout"); end
endmodule
