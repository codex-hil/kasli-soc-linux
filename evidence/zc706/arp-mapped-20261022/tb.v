module tb;
reg sys_clk=0, sys_rst=1, run=0;
reg [1:0] gap=0;
wire busy;wire [31:0] sent,received,errors,last_ip,last_mac_lo;
wire [15:0] last_mac_hi;
arp_test dut(.sys_clk(sys_clk),.sys_rst(sys_rst),.run(run),.gap(gap),
 .busy(busy),.sent(sent),.received(received),.errors(errors),
 .last_ip(last_ip),.last_mac_lo(last_mac_lo),.last_mac_hi(last_mac_hi));
always #5 sys_clk=~sys_clk;
integer n,g;
initial begin
 repeat(5) @(negedge sys_clk);sys_rst=0;
 for(g=0;g<3;g=g+1) begin
  gap=(g==2)?3:g;run=1;
  repeat(6000) @(negedge sys_clk);run=0;
  repeat(300) @(negedge sys_clk);
  $display("gap=%d sent=%d received=%d errors=%d ip=%h mac=%h%h",gap,sent,received,errors,last_ip,last_mac_hi,last_mac_lo);
  if(busy!==0 || sent<20 || received!==sent || errors!==0 || last_ip!==32'hc0a8026b || {last_mac_hi,last_mac_lo}!==48'h6c2b59f476e8)
   $fatal(1,"ARP decoded fields/count mismatch");
 end
 $display("PASS");$finish;
end
endmodule
