`timescale 1ns/1fs
module wr_pair(input sys,helper,adc,reset,output signed [31:0] phase,output valid,output [31:0] events);
 wire [31:0] tag_ref, tag_adc;
 wire stb_ref, stb_adc;
 dmtd_with_deglitcher ref_t(
  .rst_n_dmtdclk_i(!reset),.rst_n_sysclk_i(!reset),.clk_in_i(sys),.clk_dmtd_i(helper),
  .clk_dmtd_over_i(1'b0),.clk_sys_i(sys),.clk_sampled_a_i(1'b0),.resync_p_a_i(1'b0),
  .resync_p_over_i(1'b0),.r_deglitch_threshold_i(16'd4),.r_oversample_in_div_i(6'd0),
  .r_oversample_pps_div_i(6'd0),.r_samples_i(16'd0),.r_minmax_sel_i(1'b0),
  .r_stat_reset_i(1'b0),.pps_p1_i(1'b0),.tag_o(tag_ref),.tag_stb_p1_o(stb_ref));
 dmtd_with_deglitcher adc_t(
  .rst_n_dmtdclk_i(!reset),.rst_n_sysclk_i(!reset),.clk_in_i(adc),.clk_dmtd_i(helper),
  .clk_dmtd_over_i(1'b0),.clk_sys_i(sys),.clk_sampled_a_i(1'b0),.resync_p_a_i(1'b0),
  .resync_p_over_i(1'b0),.r_deglitch_threshold_i(16'd4),.r_oversample_in_div_i(6'd0),
  .r_oversample_pps_div_i(6'd0),.r_samples_i(16'd0),.r_minmax_sel_i(1'b0),
  .r_stat_reset_i(1'b0),.pps_p1_i(1'b0),.tag_o(tag_adc),.tag_stb_p1_o(stb_adc));
 wire signed [31:0] raw;
 wire [31:0] rejected,ra,aa;
 wr_phase_tracker tracker(sys,reset,stb_ref,stb_adc,tag_ref,tag_adc,phase,raw,events,rejected,ra,aa,valid);
endmodule
module wr_ddmtd_dual_tb;
 reg sys=0,helper=0,adc=0,adc2=0,reset=1,reset2=1,enable=1;
 always #5 sys=!sys;
 always #5.079365079 helper=!helper;
 always #4.999950000 if(enable) adc=!adc;
 always #5.000040000 adc2=!adc2;
 wire signed [31:0] p1,p2;
 wire v1,v2;
 wire [31:0] e1,e2;
 wr_pair first(sys,helper,adc,reset,p1,v1,e1);
 wr_pair second(sys,helper,adc2,reset2,p2,v2,e2);
 integer first1,first2,before2;
 real delta1,delta2;
 initial begin
  #200 reset=0;reset2=0;
  #20000;
  if(!v1 || !v2) $fatal(1,"dual tags absent");
  first1=p1;first2=p2;
  #2000000;
  delta1=(p1-first1)*10.0/63.0;delta2=(p2-first2)*10.0/63.0;
  if(delta1 < -20.5 || delta1 > -19.5 || delta2 < 15.5 || delta2 > 16.5)
   $fatal(1,"dual frequency/phase polarity failed: %f %f",delta1,delta2);
  before2=e2;enable=0;
  #200000;
  if(v1 || !v2 || e2<=before2) $fatal(1,"isolated clock loss failed");
  reset=1;enable=1;
  #200 reset=0;
  #20000;
  if(!v1 || !v2 || e2<=before2) $fatal(1,"independent reset/recovery failed");
  $display("PASS: dual WR phase drift %f/%f ns; independent loss/reset recovery",delta1,delta2);
  $finish;
 end
 initial begin #3000000;$fatal(1,"watchdog");end
endmodule
