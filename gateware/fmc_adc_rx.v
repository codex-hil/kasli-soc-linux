// SPDX-License-Identifier: BSD-2-Clause
// LTC2174: two lanes/channel, 16-bit serialization, 100 MS/s, DCO=400 MHz.
// The CERN pin convention already compensates the PCB DCO/FR polarity swaps.
module fmc_adc_rx(
    input dco_p, dco_n, frame_p, frame_n,
    input [7:0] data_p, data_n,
    input sys_clk, reset, idelay_ready,
    input [44:0] delay_taps,
    output adc_clk, output adc_reset,
    output [63:0] samples,
    output [7:0] frame,
    output reg aligned = 0
);
    wire dco, io_clk;
    IBUFDS #(.IOSTANDARD("LVDS_25"), .DIFF_TERM("TRUE")) dco_ibuf
        (.I(dco_p), .IB(dco_n), .O(dco));

    // Zynq openXC7 lacks BUFR metadata. MMCM/BUFG clocks also avoid the
    // unroutable shared pad-to-BUFIO/MMCM branch in the pinned flow.
    wire divided, serial_clock, feedback, feedback_buffered, locked;
    MMCME2_ADV #(.CLKIN1_PERIOD(2.5), .DIVCLK_DIVIDE(1),
        .CLKFBOUT_MULT_F(2.0), .CLKOUT0_DIVIDE_F(8.0), .CLKOUT1_DIVIDE(2),
        .BANDWIDTH("OPTIMIZED"), .COMPENSATION("ZHOLD")) dco_mmcm
        (.CLKIN1(dco), .CLKINSEL(1'b1),
         .CLKFBIN(feedback_buffered), .CLKFBOUT(feedback),
         .CLKOUT0(divided), .CLKOUT1(serial_clock), .LOCKED(locked), .RST(reset), .PWRDWN(1'b0),
         .DCLK(1'b0), .DEN(1'b0), .DWE(1'b0), .DADDR(7'b0), .DI(16'b0),
         .PSCLK(1'b0), .PSEN(1'b0), .PSINCDEC(1'b0));
    BUFG dco_serial(.I(serial_clock), .O(io_clk));
    BUFG dco_feedback(.I(feedback), .O(feedback_buffered));
    BUFG dco_divided(.I(divided), .O(adc_clk));

    // Async assertion, synchronous release in the divided DCO domain.
    reg [3:0] reset_pipe = 4'hf;
    wire clock_reset = reset || !locked;
    always @(posedge adc_clk or posedge clock_reset)
        if (clock_reset) reset_pipe <= 4'hf;
        else reset_pipe <= {reset_pipe[2:0], !idelay_ready};
    wire rx_reset = reset_pipe[3];
    assign adc_reset = rx_reset;
    wire [8:0] pins_p = {frame_p, data_p};
    wire [8:0] pins_n = {frame_n, data_n};
    wire [7:0] parallel [0:8];
    reg bitslip = 0;
    reg [4:0] settle = 0;
    reg [3:0] good = 0;
    always @(posedge adc_clk or posedge rx_reset) begin
        bitslip <= 0;
        if (rx_reset) begin
            settle <= 0;
            good <= 0;
            aligned <= 0;
        end else if (settle != 0) begin
            settle <= settle - 1'b1;
        end else if (frame == 8'h0f) begin
            if (good != 15) good <= good + 1'b1;
            if (good >= 7) aligned <= 1;
        end else begin
            good <= 0;
            aligned <= 0;
            bitslip <= 1;
            // DDR BITSLIP is alternating +1/-3; allow pipeline to settle.
            settle <= 15;
        end
    end
    genvar lane, bitnum, channel;
    generate for (lane=0; lane<9; lane=lane+1) begin: lanes
        wire raw, delayed;
        IBUFDS #(.IOSTANDARD("LVDS_25"), .DIFF_TERM("TRUE")) ibuf
            (.I(pins_p[lane]), .IB(pins_n[lane]), .O(raw));
        IDELAYE2 #(.DELAY_SRC("IDATAIN"), .IDELAY_TYPE("VAR_LOAD"),
            .IDELAY_VALUE(0), .HIGH_PERFORMANCE_MODE("TRUE"),
            .REFCLK_FREQUENCY(200.0), .SIGNAL_PATTERN("DATA")) delay
            (.IDATAIN(raw), .DATAIN(1'b0), .DATAOUT(delayed),
             .C(sys_clk), .CE(1'b0), .INC(1'b0), .LD(1'b1),
             .LDPIPEEN(1'b0), .REGRST(1'b0), .CINVCTRL(1'b0),
             .CNTVALUEIN(delay_taps[5*lane+:5]), .CNTVALUEOUT());
        ISERDESE2 #(.DATA_RATE("DDR"), .DATA_WIDTH(8),
            .INTERFACE_TYPE("NETWORKING"), .IOBDELAY("IFD"),
            .NUM_CE(2), .SERDES_MODE("MASTER")) serdes
            (.DDLY(delayed), .CLK(io_clk), .CLKB(~io_clk),
             .CLKDIV(adc_clk),
             .CE1(1'b1), .CE2(1'b1), .RST(rx_reset), .BITSLIP(bitslip),
             .DYNCLKDIVSEL(1'b0), .DYNCLKSEL(1'b0),
             // Cascade inputs are unused for width-8 MASTER; leave them open.
             .SHIFTOUT1(), .SHIFTOUT2(), .O(),
             .Q1(parallel[lane][0]), .Q2(parallel[lane][1]),
             .Q3(parallel[lane][2]), .Q4(parallel[lane][3]),
             .Q5(parallel[lane][4]), .Q6(parallel[lane][5]),
             .Q7(parallel[lane][6]), .Q8(parallel[lane][7]));
    end endgenerate
    assign frame = parallel[8];
    // LSB-first vector: B is even bits, A odd bits; ADC data is left justified.
    generate for (channel=0; channel<4; channel=channel+1) begin: decode
        for (bitnum=0; bitnum<8; bitnum=bitnum+1) begin: bits
            assign samples[channel*16+2*bitnum] = parallel[2*channel][bitnum];
            assign samples[channel*16+2*bitnum+1] = parallel[2*channel+1][bitnum];
        end
    end endgenerate
endmodule
