// SPDX-License-Identifier: BSD-2-Clause
// One frozen 1024x64 snapshot. Software owns it until the next arm request.
// arm_toggle is synchronized; ext_mode is held stable before and during capture.
module fmc_adc_capture(
    input sys_clk, adc_clk, reset,
    input arm_toggle, ext_mode, trigger,
    input aligned, input [7:0] frame, input [63:0] samples,
    input [9:0] read_address,
    output reg [63:0] read_data,
    output reg done_toggle = 0,
    output reg [10:0] captured = 0,
    output reg [10:0] errors = 0,
    output [31:0] sample_gray
);
    reg [63:0] memory [0:1023];
    always @(posedge sys_clk) read_data <= memory[read_address];
    (* ASYNC_REG="TRUE" *) reg [1:0] request_sync = 0;
    (* ASYNC_REG="TRUE" *) reg [1:0] mode_sync = 0;
    reg previous_trigger = 0;
    reg [1:0] state = 0;
    reg request = 0;
    reg [9:0] address = 0;
    // Separate the RAM port from asynchronously reset control logic so Yosys
    // infers true dual-clock block RAM, rather than resetting 65536 flip-flops.
    always @(posedge adc_clk)
        if (!reset && state == 2) memory[address] <= samples;
    reg [31:0] sample_count = 0;
    // Registered Gray encoding: no glitches at CDC launch.
    reg [31:0] gray = 0;
    assign sample_gray = gray;
    wire [31:0] next_count = sample_count + 1'b1;
    always @(posedge adc_clk or posedge reset) begin
        if (reset) begin
            request_sync <= 0; mode_sync <= 0;
            previous_trigger <= 0; state <= 0; request <= 0;
            address <= 0; done_toggle <= 0; captured <= 0; errors <= 0;
            sample_count <= 0; gray <= 0;
        end else begin
            request_sync <= {request_sync[0], arm_toggle};
            mode_sync <= {mode_sync[0], ext_mode};
            previous_trigger <= trigger;
            sample_count <= next_count;
            gray <= next_count ^ (next_count >> 1);
            case (state)
                0: if (request_sync[1] != done_toggle) begin
                    request <= request_sync[1]; captured <= 0; errors <= 0;
                    address <= 0; state <= 1;
                end
                1: if (aligned && (!mode_sync[1] || (trigger && !previous_trigger)))
                    state <= 2;
                2: begin
                    captured <= captured + 1'b1;
                    if (!aligned || frame != 8'h0f) errors <= errors + 1'b1;
                    if (address == 1023) begin
                        done_toggle <= request;
                        state <= 0;
                    end else address <= address + 1'b1;
                end
            endcase
        end
    end
endmodule
