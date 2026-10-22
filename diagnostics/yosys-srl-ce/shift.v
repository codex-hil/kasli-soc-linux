module shift(input clk, ce, d, output q);
  reg [6:0] stages = 0;
  always @(posedge clk)
    if (ce) stages <= {stages[5:0], d};
  assign q = stages[6];
endmodule
