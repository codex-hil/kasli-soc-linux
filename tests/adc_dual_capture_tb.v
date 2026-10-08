`timescale 1ns/1ps
// Two distinct asynchronous sample domains; no common sample epoch is assumed.
module tb;
    reg sys_clk=0, clk1=0, clk2=0;
    always #5 sys_clk=~sys_clk;
    always #4.9 clk1=~clk1;
    always #5.1 clk2=~clk2;
    reg reset1=1, reset2=1, arm1=0, arm2=0;
    reg [63:0] sample1=64'h1000, sample2=64'h9000;
    always @(negedge clk1) sample1 <= sample1+1;
    always @(negedge clk2) sample2 <= sample2+3;
    reg [9:0] address1=0, address2=0;
    wire [63:0] data1, data2;
    wire done1, done2;
    wire [10:0] captured1,captured2,errors1,errors2;
    wire [31:0] gray1,gray2;
    fmc_adc_capture card1(sys_clk,clk1,reset1,arm1,1'b0,1'b0,1'b1,8'h0f,
        sample1,address1,data1,done1,captured1,errors1,gray1);
    fmc_adc_capture card2(sys_clk,clk2,reset2,arm2,1'b0,1'b0,1'b1,8'h0f,
        sample2,address2,data2,done2,captured2,errors2,gray2);
    reg [63:0] expected1 [0:1023], expected2 [0:1023];
    integer writes1=0,writes2=0,i;
    always @(posedge clk1) if(!reset1 && card1.state==2) begin
        expected1[writes1]=sample1; writes1=writes1+1;
    end
    always @(posedge clk2) if(!reset2 && card2.state==2) begin
        expected2[writes2]=sample2; writes2=writes2+1;
    end
    initial begin
        #37 reset1=0; reset2=0;
        #43 arm1=1;
        #79 arm2=1;
        wait(writes2==100);
        // Abort/re-arm HPC while LPC keeps acquiring.
        #1 reset2=1; arm2=0;
        #30 writes2=0; reset2=0;
        repeat(8) @(negedge sys_clk);
        arm2=1;
        wait(done1 && done2);
        if(writes1!=1024 || writes2!=1024 || captured1!=1024 || captured2!=1024)
            $fatal(1,"independent capture length mismatch");
        if(errors1!=0 || errors2!=0) $fatal(1,"unexpected frame errors");
        for(i=0;i<1024;i=i+1) begin
            @(negedge sys_clk); address1=i; address2=1023-i;
            repeat(2) @(posedge sys_clk);
            @(negedge sys_clk);
            if(data1!==expected1[i] || data2!==expected2[1023-i])
                $fatal(1,"cross-card buffer corruption at sample %0d",i);
        end
        repeat(30) @(posedge sys_clk);
        if(writes1!=1024 || writes2!=1024) $fatal(1,"frozen buffer changed");
        $display("PASS: two asynchronous cards, overlapping captures, HPC abort/re-arm isolation, 2048 exact samples, frozen buffers");
        $finish;
    end
    initial begin #1000000; $fatal(1,"dual capture timeout"); end
endmodule
