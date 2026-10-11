// SPDX-License-Identifier: BSD-2-Clause
// WR tag delivery is much slower than this four-stage pipeline (1/64 SYS).
// Continuous unwrapping preserves whole-cycle slips across slow Linux polls.
module wr_phase_tracker(
    input wire clk, reset, ref_strobe, adc_strobe,
    input wire [31:0] ref_tag, adc_tag,
    output reg signed [31:0] phase_ticks,
    output reg signed [31:0] raw_ticks,
    output reg [31:0] events, rejected,
    output reg [31:0] ref_age, adc_age,
    output wire valid
);
    reg [31:0] last_ref;
    reg have_ref, have_phase;
    reg signed [7:0] difference, normalized_reg, previous, step_reg, raw_reg;
    reg [2:0] pipe;
    // Adjacent WR events are separated by 63 helper ticks. Signed low-byte
    // subtraction is exact for the expected +/-63 interval, including wrap.
    wire signed [7:0] next_difference = adc_tag[7:0] - (ref_strobe ? ref_tag[7:0] : last_ref[7:0]);
    wire signed [7:0] normalized1 = difference > 31 ? difference-8'sd63 :
        difference < -31 ? difference+8'sd63 : difference;
    wire signed [7:0] normalized = normalized1 > 31 ? normalized1-8'sd63 :
        normalized1 < -31 ? normalized1+8'sd63 : normalized1;
    wire signed [7:0] step0 = normalized_reg - previous;
    wire signed [7:0] step = step0 > 31 ? step0-8'sd63 : step0 < -31 ? step0+8'sd63 : step0;
    reg first_reg;
    assign valid = have_phase && ref_age < 10000 && adc_age < 10000;
    always @(posedge clk) begin
        if (reset) begin
            have_ref <= 0; have_phase <= 0; last_ref <= 0; previous <= 0;
            phase_ticks <= 0; raw_ticks <= 0; events <= 0; rejected <= 0;
            difference <= 0; normalized_reg <= 0; step_reg <= 0; raw_reg <= 0;
            pipe <= 0; first_reg <= 0;
            ref_age <= 32'hffffffff; adc_age <= 32'hffffffff;
        end else begin
            pipe <= {pipe[1:0], 1'b0};
            if (ref_age != 32'hffffffff) ref_age <= ref_age+1;
            if (adc_age != 32'hffffffff) adc_age <= adc_age+1;
            if (ref_strobe) begin last_ref <= ref_tag; have_ref <= 1; ref_age <= 0; end
            if (adc_strobe) begin
                adc_age <= 0;
                if ((have_ref || ref_strobe) && pipe == 0 && ref_age < 10000 &&
                    next_difference >= -126 && next_difference <= 126) begin
                    difference <= next_difference; pipe[0] <= 1;
                end else rejected <= rejected+1;
            end
            if (pipe[0]) normalized_reg <= normalized;
            if (pipe[1]) begin
                step_reg <= step; raw_reg <= normalized_reg;
                previous <= normalized_reg; first_reg <= !have_phase;
            end
            if (pipe[2]) begin
                phase_ticks <= first_reg ? $signed(raw_reg) : phase_ticks+$signed(step_reg);
                raw_ticks <= $signed(raw_reg); have_phase <= 1; events <= events+1;
            end
        end
    end
endmodule
