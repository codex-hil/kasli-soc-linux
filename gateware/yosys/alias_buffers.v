// SPDX-License-Identifier: BSD-2-Clause
// Identity-only alias removal; do not buffer-normalize physical inout nets.
(* techmap_celltype = "$buf" *)
module alias_buffer #(parameter WIDTH = 1)(input [WIDTH-1:0] A, output [WIDTH-1:0] Y);
    assign Y = A;
endmodule
(* techmap_celltype = "$_BUF_" *)
module alias_buffer_bit(input A, output Y);
    assign Y = A;
endmodule
