`timescale 1ns/1ps
// PS7 is a black box. This tests emitted PL RTL, not PS7 or physical hardware.
module tb;
    reg clk = 0;
    always #5 clk = ~clk;
    top dut();
    always @(clk) force dut.PS7.FCLKCLK = {3'b0, clk};
    reg awvalid=0, wvalid=0, bready=0, arvalid=0, rready=0;
    reg [31:0] awaddr=0, wdata=0, araddr=0;
    reg [3:0] strobe=15;
    reg [3:0] resetn=0;
    reg [31:0] value, result, original;
    integer i;

    task write_word(input [31:0] address, input [31:0] data);
        begin
            @(negedge clk); awaddr=address; awvalid=1;
            @(posedge clk);
            while (!dut.PS7.MAXIGP0AWREADY) @(posedge clk);
            @(negedge clk); awvalid=0;
            repeat (i % 5) @(negedge clk);
            wdata=data; wvalid=1;
            @(posedge clk);
            while (!dut.PS7.MAXIGP0WREADY) @(posedge clk);
            @(negedge clk); wvalid=0;
            repeat (i % 7) @(negedge clk);
            bready=1;
            @(posedge clk);
            while (!dut.PS7.MAXIGP0BVALID) @(posedge clk);
            if (dut.PS7.MAXIGP0BRESP !== 0) $fatal(1,"write response error");
            if (dut.PS7.MAXIGP0BID !== 7) $fatal(1,"write ID error");
            @(negedge clk); bready=0;
        end
    endtask

    task read_word(input [31:0] address, output [31:0] data);
        begin
            @(negedge clk); araddr=address; arvalid=1;
            @(posedge clk);
            while (!dut.PS7.MAXIGP0ARREADY) @(posedge clk);
            @(negedge clk); arvalid=0;
            repeat (i % 7) @(negedge clk);
            rready=1;
            @(posedge clk);
            while (!dut.PS7.MAXIGP0RVALID) @(posedge clk);
            if (dut.PS7.MAXIGP0RRESP !== 0 || dut.PS7.MAXIGP0RLAST !== 1)
                $fatal(1,"read response error");
            if (dut.PS7.MAXIGP0RID !== 3) $fatal(1,"read ID error");
            data=dut.PS7.MAXIGP0RDATA;
            @(negedge clk); rready=0;
        end
    endtask

    initial begin
        force dut.PS7.FCLKRESETN = resetn;
        force dut.PS7.MAXIGP0AWVALID = awvalid;
        force dut.PS7.MAXIGP0AWADDR = awaddr;
        force dut.PS7.MAXIGP0AWSIZE = 3'd2;
        force dut.PS7.MAXIGP0AWLEN = 4'd0;
        force dut.PS7.MAXIGP0AWBURST = 2'd1;
        force dut.PS7.MAXIGP0AWID = 12'd7;
        force dut.PS7.MAXIGP0WVALID = wvalid;
        force dut.PS7.MAXIGP0WDATA = wdata;
        force dut.PS7.MAXIGP0WSTRB = strobe;
        force dut.PS7.MAXIGP0WLAST = 1'b1;
        force dut.PS7.MAXIGP0WID = 12'd7;
        force dut.PS7.MAXIGP0BREADY = bready;
        force dut.PS7.MAXIGP0ARVALID = arvalid;
        force dut.PS7.MAXIGP0ARADDR = araddr;
        force dut.PS7.MAXIGP0ARSIZE = 3'd2;
        force dut.PS7.MAXIGP0ARLEN = 4'd0;
        force dut.PS7.MAXIGP0ARBURST = 2'd1;
        force dut.PS7.MAXIGP0ARID = 12'd3;
        force dut.PS7.MAXIGP0RREADY = rready;
        repeat(10) @(negedge clk); resetn=15;
        repeat(10) @(negedge clk);
        i=0;
        read_word(32'h40000808,result);
        if (result !== 32'h4b534f43) $fatal(1,"signature mismatch %h",result);
        read_word(32'h40000804,original);
        for(i=0;i<1000;i=i+1) begin
            value=$random;
            write_word(32'h40000800,value);
            read_word(32'h40000800,result);
            if(result !== value) $fatal(1,"scratch mismatch %h != %h",result,value);
        end
        read_word(32'h40000804,result);
        if(result <= original) $fatal(1,"counter did not advance");
        $display("PASS: 1000 AXI/CSR transactions with delayed channels and response backpressure (simulation)");
        $finish;
    end
    initial begin #1000000; $fatal(1,"AXI test timeout"); end
endmodule
