// SPDX-License-Identifier: BSD-2-Clause
// Count exactly gate_cycles edges in a measured domain; timestamp both
// boundaries in ref_clk. Only event toggles cross back, never binary counters.
module reciprocal_counter #(
    parameter TIMEOUT_TICKS = 300000000,
    parameter MAX_GATE = 200000000
)(
    input wire ref_clk, reset, measured_clk, start,
    input wire [31:0] gate_cycles,
    output reg busy, valid,
    output reg [1:0] error, // 1: missing/slow clock, 2: invalid gate
    output reg [31:0] reference_ticks, measured_cycles, sequence_id
);
    reg request = 0;
    reg [31:0] held_gate = 0;
    // Stable bundled data: held_gate is set when request changes and remains
    // unchanged until completion. Two request synchronizers + four settling
    // cycles precede its sampling in the measured domain.
    (* ASYNC_REG = "TRUE" *) reg [1:0] request_sync = 0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_release = 0;
    reg seen_request = 0, start_event = 0, stop_event = 0;
    reg [2:0] settling = 0;
    reg running = 0;
    reg [31:0] remaining = 0;
    always @(posedge measured_clk or posedge reset)
        if (reset) reset_release <= 0;
        else reset_release <= {reset_release[0], 1'b1};
    // Async assertion works even with a missing measured clock. Deassertion
    // is synchronized locally. Software reset is the explicit timeout recovery.
    wire measured_reset = !reset_release[1];
    always @(posedge measured_clk or posedge measured_reset) begin
        if (measured_reset) begin
            request_sync <= 0; seen_request <= 0;
            start_event <= 0; stop_event <= 0;
            settling <= 0; running <= 0; remaining <= 0;
        end else begin
            request_sync <= {request_sync[0], request};
            if (!running) begin
                if (request_sync[1] != seen_request) begin
                    if (settling == 4) begin
                        seen_request <= request_sync[1];
                        start_event <= request_sync[1];
                        remaining <= held_gate - 1;
                        running <= 1;
                        settling <= 0;
                    end else settling <= settling + 1;
                end
            end else if (remaining == 0) begin
                stop_event <= seen_request;
                running <= 0;
            end else remaining <= remaining - 1;
        end
    end
    (* ASYNC_REG = "TRUE" *) reg [1:0] start_sync = 0, stop_sync = 0;
    reg [31:0] reference_counter = 0, command_time = 0, first_time = 0;
    reg started = 0;
    always @(posedge ref_clk) begin
        if (reset) begin
            request <= 0; held_gate <= 0;
            start_sync <= 0; stop_sync <= 0;
            reference_counter <= 0; command_time <= 0; first_time <= 0;
            started <= 0; busy <= 0; valid <= 0; error <= 0;
            reference_ticks <= 0; measured_cycles <= 0; sequence_id <= 0;
        end else begin
            reference_counter <= reference_counter + 1;
            start_sync <= {start_sync[0], start_event};
            stop_sync <= {stop_sync[0], stop_event};
            if (start && !busy && error == 0) begin
                valid <= 0;
                if (gate_cycles < 16 || gate_cycles > MAX_GATE) begin
                    error <= 2; sequence_id <= sequence_id + 1;
                end else begin
                    held_gate <= gate_cycles; request <= !request;
                    command_time <= reference_counter;
                    busy <= 1; started <= 0;
                end
            end
            if (busy) begin
                if (!started && start_sync[1] == request) begin
                    first_time <= reference_counter;
                    started <= 1;
                end
                if (started && stop_sync[1] == request) begin
                    reference_ticks <= reference_counter - first_time;
                    measured_cycles <= held_gate;
                    busy <= 0; valid <= 1; sequence_id <= sequence_id + 1;
                end else if (reference_counter - command_time >= TIMEOUT_TICKS) begin
                    busy <= 0; valid <= 0; error <= 1;
                    sequence_id <= sequence_id + 1;
                end
            end
        end
    end
endmodule
