`timescale 1ns/1fs
module wr_ddmtd_tb;
 reg sys=0, helper=0, adc=0, reset=1, adc_enable=1;
 always #5 sys=!sys;
 always #5.079365079 helper=!helper;
 // +10 ppm feedback frequency; the phase must advance, not wrap unnoticed.
 always #4.999950000 if(adc_enable) adc=!adc;
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
 wire signed [31:0] phase, raw;
 wire [31:0] events,rejected,ra,aa;
 wire valid;
 wr_phase_tracker tracker(sys,reset,stb_ref,stb_adc,tag_ref,tag_adc,phase,raw,events,rejected,ra,aa,valid);
 integer first;
 real delta_ns;
 initial begin
  #200 reset=0;
  #20000;
  if(!valid) $fatal(1,"no phase tags");
  first=phase;
  #2000000;
  delta_ns=(phase-first)*10.0/63.0;
  $display("phase drift %f ns, events %d, rejected %d",delta_ns,events,rejected);
  if (!valid || rejected>2 || events<2000 || delta_ns < -20.5 || delta_ns > -19.5)
   $fatal(1,"WR tag/unwrapping frequency/phase relation failed");
  adc_enable=0;
  #200000;
  if(valid) $fatal(1,"phase valid survived missing ADC tags");
  reset=1; adc_enable=1;
  #200 reset=0;
  #20000;
  if(!valid) $fatal(1,"phase failed to recover after reset and clock return");
  $display("PASS: original WR taggers, phase polarity, unwrap, loss and recovery");
  $finish;
 end
 initial begin #3000000; $fatal(1,"watchdog"); end
endmodule
