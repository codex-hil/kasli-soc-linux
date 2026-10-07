`timescale 1ns/1ps
// Protocol-level models ONLY: no FPGA timing, analog delay, or calibration.
// Used to check frame acquisition and lane/bit ordering in fmc_adc_rx.v.
module IBUFDS #(parameter IOSTANDARD="", DIFF_TERM="FALSE")
    (input I, IB, output O);
    assign O=I;
endmodule
module BUFIO(input I, output O); assign O=I; endmodule
module BUFG(input I, output O); assign O=I; endmodule
module MMCME2_ADV #(parameter CLKIN1_PERIOD=2.5, DIVCLK_DIVIDE=1,
    CLKFBOUT_MULT_F=2.0, CLKOUT0_DIVIDE_F=8.0, CLKOUT1_DIVIDE=2, BANDWIDTH="OPTIMIZED", COMPENSATION="ZHOLD")
    (input CLKIN1, CLKIN2, CLKINSEL, CLKFBIN, RST, PWRDWN, DCLK, DEN, DWE,
     input [6:0] DADDR, input [15:0] DI, input PSCLK, PSEN, PSINCDEC,
     output CLKFBOUT, CLKOUT0, CLKOUT1, LOCKED);
    reg [1:0] divider=0;
    always @(posedge CLKIN1 or posedge RST)
        if(RST) divider<=0;
        else divider<=divider+1'b1;
    assign CLKOUT0=divider[1] & !RST;
    assign CLKFBOUT=CLKIN1;
    assign CLKOUT1=CLKIN1;
    assign LOCKED=!RST && !PWRDWN;
endmodule
module IDELAYE2 #(parameter DELAY_SRC="IDATAIN", IDELAY_TYPE="VAR_LOAD",
    IDELAY_VALUE=0, HIGH_PERFORMANCE_MODE="TRUE", REFCLK_FREQUENCY=200.0, SIGNAL_PATTERN="DATA")
    (input IDATAIN,DATAIN,C,CE,INC,LD,LDPIPEEN,REGRST,CINVCTRL,
     input [4:0] CNTVALUEIN,output [4:0] CNTVALUEOUT,output DATAOUT);
    assign DATAOUT=IDATAIN;
    assign CNTVALUEOUT=CNTVALUEIN;
endmodule
module ISERDESE2 #(parameter DATA_RATE="DDR", DATA_WIDTH=8,
    INTERFACE_TYPE="NETWORKING", IOBDELAY="IFD", NUM_CE=2, SERDES_MODE="MASTER")
    (input D,DDLY,CLK,CLKB,CLKDIV,CLKDIVP,OCLK,OCLKB,CE1,CE2,RST,BITSLIP,
     DYNCLKDIVSEL,DYNCLKSEL,OFB,SHIFTIN1,SHIFTIN2,
     output SHIFTOUT1,SHIFTOUT2,O,Q1,Q2,Q3,Q4,Q5,Q6,Q7,Q8);
    reg [15:0] history=0;
    reg [7:0] parallel=0;
    integer slip=0;
    reg alternate=0;
    always @(posedge CLK or negedge CLK)
        if(RST) history<=0;
        else if(CE1 && CE2) history<={history[14:0],DDLY};
    always @(posedge CLKDIV or posedge RST)
        if(RST) begin parallel<=0; slip=0; alternate=0; end
        else begin
            parallel <= history >> slip;
            if(BITSLIP) begin
                slip=(slip+(alternate ? 5 : 1)) % 8;
                alternate=~alternate;
            end
        end
    assign {Q8,Q7,Q6,Q5,Q4,Q3,Q2,Q1}=parallel;
    assign SHIFTOUT1=0; assign SHIFTOUT2=0; assign O=DDLY;
endmodule
