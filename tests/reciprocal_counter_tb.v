`timescale 1ns/1ps
module reciprocal_counter_tb;
    reg refclk=0, clk1=0, clk2=0, enable1=1;
    always #5 refclk = !refclk;
    always #4.998 if (enable1) clk1 = !clk1;
    always #5.003 clk2 = !clk2;
    reg reset=1, start=0;
    reg [31:0] gate=1000;
    wire busy1, valid1, busy2, valid2;
    wire [1:0] error1, error2;
    wire [31:0] ticks1, ticks2, cycles1, cycles2, seq1, seq2;
    reciprocal_counter #(.TIMEOUT_TICKS(3000), .MAX_GATE(2000)) a(
        refclk, reset, clk1, start, gate, busy1, valid1, error1, ticks1, cycles1, seq1);
    reciprocal_counter #(.TIMEOUT_TICKS(3000), .MAX_GATE(2000)) b(
        refclk, reset, clk2, start, gate, busy2, valid2, error2, ticks2, cycles2, seq2);
    task clear;
        begin
            @(negedge refclk); reset=1; start=0;
            repeat(6) @(negedge refclk);
            reset=0; repeat(12) @(negedge refclk);
        end
    endtask
    task launch;
        begin
            @(negedge refclk); start=1;
            @(negedge refclk); start=0;
        end
    endtask
    task finish;
        integer watchdog;
        begin
            watchdog=0;
            while(busy1 || busy2) begin
                @(negedge refclk); watchdog=watchdog+1;
                if (watchdog>3100) $fatal(1,"completion stalled");
            end
        end
    endtask
    task check;
        real expected1, expected2;
        begin
            expected1=cycles1*9.996/10.0;
            expected2=cycles2*10.006/10.0;
            if (!valid1 || !valid2 || error1 || error2 ||
                ticks1<expected1-2 || ticks1>expected1+2 ||
                ticks2<expected2-2 || ticks2>expected2+2)
                $fatal(1,"reciprocal result: %d/%d expected %f/%f",ticks1,ticks2,expected1,expected2);
        end
    endtask
    integer n;
    initial begin
        clear();
        for(n=0;n<12;n=n+1) begin
            gate=1000+n*17;
            launch();
            repeat(30) @(negedge refclk);
            // An overlapping command and changed CSR must not corrupt the
            // exact gate length latched by the original accepted command.
            gate=16; launch(); finish(); check();
            if (cycles1 != 1000+n*17 || seq1 != n+1 || seq2 != n+1)
                $fatal(1,"busy command or coherent gate failure");
        end
        clear();
        a.reference_counter=32'hfffffe00;
        b.reference_counter=32'hfffffe00;
        gate=1000; launch(); finish(); check();
        clear(); gate=15; launch();
        if(error1!=2 || error2!=2 || valid1 || busy1) $fatal(1,"invalid gate accepted");
        clear(); gate=2001; launch();
        if(error1!=2 || error2!=2 || valid1 || busy1) $fatal(1,"oversize gate accepted");
        clear(); gate=1000; launch();
        repeat(40) @(negedge refclk);
        enable1=0; finish();
        if(error1!=1 || valid1 || !valid2 || error2) $fatal(1,"mid-gate clock loss failed");
        clear(); enable1=0; gate=1000; launch(); finish();
        if(error1!=1 || valid1 || !valid2 || error2) $fatal(1,"missing-clock isolation failed");
        // A reset must recover a stalled channel even without its clock.
        clear(); enable1=1; repeat(20) @(negedge refclk);
        launch(); finish(); check();
        $display("PASS: asynchronous frequency/phase, exact N, busy rejection, wrap, invalid gate, missing clock, reset recovery");
        $finish;
    end
    initial begin #1000000; $fatal(1,"global watchdog"); end
endmodule
