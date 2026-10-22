module tb;
reg clk=0, ce=0, d=0;
wire q;
reg [6:0] golden=0;
integer n;
reg [15:0] stimulus=16'hace1;
shift dut(.clk(clk),.ce(ce),.d(d),.q(q));
always #5 clk=~clk;
always @(posedge clk) if(ce) golden <= {golden[5:0],d};
initial begin
 for(n=0;n<200;n=n+1) begin
  @(negedge clk); ce=(n%7)!=3 && (n%7)!=4; d=stimulus[0];
  stimulus={stimulus[14:0],stimulus[15]^stimulus[13]^stimulus[12]^stimulus[10]};
  @(posedge clk); #1;
  if(q!==golden[6]) begin
   $display("FAIL cycle=%0d ce=%b q=%b expected=%b",n,ce,q,golden[6]);
   $fatal(1,"clock enable was not preserved");
  end
 end
 $display("PASS enabled seven-stage shift"); $finish;
end
endmodule
