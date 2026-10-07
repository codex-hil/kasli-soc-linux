`timescale 1ns/1ps
module tb;
    reg sys_clk=0, dco=0, reset=1, ready=0, corrupt_frame=0;
    always #5 sys_clk=~sys_clk;
    reg [7:0] data=0;
    reg serial_frame=0;
    reg [63:0] pattern=64'h4560123489accde0;
    wire adc_clk, adc_reset, aligned;
    wire [63:0] samples;
    wire [7:0] frame;
    fmc_adc_rx dut(dco,~dco,serial_frame,~serial_frame,data,~data,sys_clk,
                  reset,ready,45'b0,adc_clk,adc_reset,samples,frame,aligned);
    integer b=7,ch,i;
    initial forever begin
        // ADC changes serial data between DCO sampling edges.
        for(ch=0;ch<4;ch=ch+1) begin
            data[2*ch]=pattern[16*ch+2*b];
            data[2*ch+1]=pattern[16*ch+2*b+1];
        end
        serial_frame=corrupt_frame ? 0 : ((8'h0f >> b) & 1);
        #0.6 dco=~dco;
        #0.65;
        b=(b==0) ? 7 : b-1;
    end
    task check_pattern;
        begin
            repeat(20) @(posedge adc_clk);
            if(!aligned) $fatal(1,"receiver not aligned");
            for(i=0;i<32;i=i+1) begin
                @(negedge adc_clk);
                if(frame !== 8'h0f || samples !== pattern)
                    $fatal(1,"lane decode mismatch %h != %h frame %h",samples,pattern,frame);
            end
        end
    endtask
    initial begin
        #50 ready=1; reset=0;
        wait(aligned);
        check_pattern;
        for(integer bitno=2;bitno<16;bitno=bitno+1) begin
            pattern=(64'h0001000100010001 << bitno);
            check_pattern;
            pattern=~pattern & 64'hfffcfffcfffcfffc;
            check_pattern;
        end
        corrupt_frame=1;
        repeat(40) @(posedge adc_clk);
        if(aligned) $fatal(1,"bad frame still aligned");
        corrupt_frame=0;
        wait(aligned);
        check_pattern;
        $display("PASS: frame BITSLIP acquisition/recovery, 4-channel lane ordering, walking bits (protocol model)");
        $finish;
    end
    initial begin #100000; $fatal(1,"receiver timeout"); end
endmodule
