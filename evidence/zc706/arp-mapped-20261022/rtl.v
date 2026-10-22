/* Machine-generated using Migen */
module arp_test(
	input run,
	input [1:0] gap,
	output reg busy,
	output reg [31:0] sent,
	output reg [31:0] received,
	output reg [31:0] errors,
	output reg [31:0] last_ip,
	output reg [31:0] last_mac_lo,
	output reg [15:0] last_mac_hi,
	input sys_clk,
	input sys_rst
);

reg sink_sink_valid;
wire sink_sink_ready;
reg sink_sink_first = 1'd0;
wire sink_sink_last;
wire [15:0] sink_sink_payload_ethernet_type;
wire [47:0] sink_sink_payload_sender_mac;
wire [47:0] sink_sink_payload_target_mac;
wire [7:0] sink_sink_payload_data;
wire sink_sink_payload_be;
wire sink_sink_payload_error;
reg source_source_valid;
wire source_source_ready;
reg source_source_payload_reply;
reg source_source_payload_request;
wire [31:0] source_source_payload_ip_address;
wire [47:0] source_source_payload_mac_address;
wire depacketizer_sink_valid;
reg depacketizer_sink_ready;
wire depacketizer_sink_first;
wire depacketizer_sink_last;
wire [15:0] depacketizer_sink_payload_ethernet_type;
wire [47:0] depacketizer_sink_payload_sender_mac;
wire [47:0] depacketizer_sink_payload_target_mac;
wire [7:0] depacketizer_sink_payload_data;
wire depacketizer_sink_payload_be;
wire depacketizer_sink_payload_error;
reg depacketizer_source_valid;
reg depacketizer_source_ready;
reg depacketizer_source_first;
reg depacketizer_source_last;
reg [7:0] depacketizer_source_payload_data;
wire depacketizer_source_payload_be;
wire depacketizer_source_payload_error;
wire [7:0] depacketizer_source_param_hwsize;
wire [15:0] depacketizer_source_param_hwtype;
wire [15:0] depacketizer_source_param_opcode;
wire [15:0] depacketizer_source_param_proto;
wire [7:0] depacketizer_source_param_protosize;
wire [31:0] depacketizer_source_param_sender_ip;
wire [47:0] depacketizer_source_param_sender_mac;
wire [31:0] depacketizer_source_param_target_ip;
wire [47:0] depacketizer_source_param_target_mac;
wire [223:0] depacketizer_header;
reg [223:0] depacketizer_sr = 224'd0;
reg depacketizer_sr_shift;
reg depacketizer_sr_shift_leftover = 1'd0;
reg [4:0] depacketizer_count = 5'd0;
reg depacketizer_data_copy_first = 1'd0;
wire depacketizer_sink_be;
reg depacketizer_source_be;
reg depacketizer_fsm_from_idle = 1'd0;
reg valid = 1'd0;
reg reply;
reg request;
reg [5:0] index = 6'd0;
reg [1:0] gap_count = 2'd0;
reg [5:0] wait_count = 6'd0;
reg [1:0] liteetharpdepacketizer_state = 2'd0;
reg [1:0] liteetharpdepacketizer_next_state;
reg [4:0] depacketizer_count_liteetharprx_next_value0;
reg depacketizer_count_liteetharprx_next_value_ce0;
reg depacketizer_fsm_from_idle_liteetharprx_next_value1;
reg depacketizer_fsm_from_idle_liteetharprx_next_value_ce1;
reg depacketizer_data_copy_first_liteetharprx_next_value2;
reg depacketizer_data_copy_first_liteetharprx_next_value_ce2;
reg [1:0] fsm_state = 2'd0;
reg [1:0] fsm_next_state;
reg [1:0] state = 2'd0;
reg [1:0] next_state;
reg [5:0] index_fsm_next_value0;
reg index_fsm_next_value_ce0;
reg busy_status_fsm_next_value1;
reg busy_status_fsm_next_value_ce1;
reg [31:0] sent_status_fsm_t_next_value0;
reg sent_status_fsm_t_next_value_ce0;
reg [5:0] wait_count_fsm_t_next_value1;
reg wait_count_fsm_t_next_value_ce1;
reg [1:0] gap_count_fsm_f_next_value;
reg gap_count_fsm_f_next_value_ce;
wire [7:0] slice_proxy0;
wire [15:0] slice_proxy1;
wire [15:0] slice_proxy2;
wire [15:0] slice_proxy3;
wire [15:0] slice_proxy4;
wire [15:0] slice_proxy5;
wire [15:0] slice_proxy6;
wire [7:0] slice_proxy7;
wire [31:0] slice_proxy8;
wire [31:0] slice_proxy9;
wire [31:0] slice_proxy10;
wire [31:0] slice_proxy11;
wire [47:0] slice_proxy12;
wire [47:0] slice_proxy13;
wire [47:0] slice_proxy14;
wire [47:0] slice_proxy15;
wire [47:0] slice_proxy16;
wire [47:0] slice_proxy17;
wire [31:0] slice_proxy18;
wire [31:0] slice_proxy19;
wire [31:0] slice_proxy20;
wire [31:0] slice_proxy21;
wire [47:0] slice_proxy22;
wire [47:0] slice_proxy23;
wire [47:0] slice_proxy24;
wire [47:0] slice_proxy25;
wire [47:0] slice_proxy26;
wire [47:0] slice_proxy27;
reg [7:0] self;

// synthesis translate_off
reg dummy_s;
initial dummy_s <= 1'd0;
// synthesis translate_on

assign sink_sink_payload_data = self;
assign sink_sink_last = (index == 6'd45);
assign sink_sink_payload_be = 1'd1;
assign sink_sink_payload_error = 1'd0;
assign sink_sink_payload_target_mac = 42'd3027388882945;
assign sink_sink_payload_sender_mac = 47'd118933448586984;
assign sink_sink_payload_ethernet_type = 12'd2054;
assign source_source_ready = 1'd1;
assign depacketizer_sink_valid = sink_sink_valid;
assign sink_sink_ready = depacketizer_sink_ready;
assign depacketizer_sink_first = sink_sink_first;
assign depacketizer_sink_last = sink_sink_last;
assign depacketizer_sink_payload_ethernet_type = sink_sink_payload_ethernet_type;
assign depacketizer_sink_payload_sender_mac = sink_sink_payload_sender_mac;
assign depacketizer_sink_payload_target_mac = sink_sink_payload_target_mac;
assign depacketizer_sink_payload_data = sink_sink_payload_data;
assign depacketizer_sink_payload_be = sink_sink_payload_be;
assign depacketizer_sink_payload_error = sink_sink_payload_error;

// synthesis translate_off
reg dummy_d;
// synthesis translate_on
always @(*) begin
	reply <= 1'd0;
	request <= 1'd0;
	case (depacketizer_source_param_opcode)
		1'd1: begin
			request <= 1'd1;
		end
		2'd2: begin
			reply <= 1'd1;
		end
		default: begin
		end
	endcase
// synthesis translate_off
	dummy_d <= dummy_s;
// synthesis translate_on
end
assign source_source_payload_ip_address = depacketizer_source_param_sender_ip;
assign source_source_payload_mac_address = depacketizer_source_param_sender_mac;
assign depacketizer_header = depacketizer_sr;
assign depacketizer_source_param_hwsize = {slice_proxy0[7:0]};
assign depacketizer_source_param_hwtype = {slice_proxy2[7:0], slice_proxy1[15:8]};
assign depacketizer_source_param_opcode = {slice_proxy4[7:0], slice_proxy3[15:8]};
assign depacketizer_source_param_proto = {slice_proxy6[7:0], slice_proxy5[15:8]};
assign depacketizer_source_param_protosize = {slice_proxy7[7:0]};
assign depacketizer_source_param_sender_ip = {slice_proxy11[7:0], slice_proxy10[15:8], slice_proxy9[23:16], slice_proxy8[31:24]};
assign depacketizer_source_param_sender_mac = {slice_proxy17[7:0], slice_proxy16[15:8], slice_proxy15[23:16], slice_proxy14[31:24], slice_proxy13[39:32], slice_proxy12[47:40]};
assign depacketizer_source_param_target_ip = {slice_proxy21[7:0], slice_proxy20[15:8], slice_proxy19[23:16], slice_proxy18[31:24]};
assign depacketizer_source_param_target_mac = {slice_proxy27[7:0], slice_proxy26[15:8], slice_proxy25[23:16], slice_proxy24[31:24], slice_proxy23[39:32], slice_proxy22[47:40]};
assign depacketizer_sink_be = depacketizer_sink_payload_be;
assign depacketizer_source_payload_be = depacketizer_source_be;
assign depacketizer_source_payload_error = depacketizer_sink_payload_error;

// synthesis translate_off
reg dummy_d_1;
// synthesis translate_on
always @(*) begin
	depacketizer_sink_ready <= 1'd0;
	depacketizer_source_valid <= 1'd0;
	depacketizer_source_first <= 1'd0;
	depacketizer_source_last <= 1'd0;
	depacketizer_source_payload_data <= 8'd0;
	depacketizer_sr_shift <= 1'd0;
	depacketizer_source_be <= 1'd1;
	liteetharpdepacketizer_next_state <= 2'd0;
	depacketizer_count_liteetharprx_next_value0 <= 5'd0;
	depacketizer_count_liteetharprx_next_value_ce0 <= 1'd0;
	depacketizer_fsm_from_idle_liteetharprx_next_value1 <= 1'd0;
	depacketizer_fsm_from_idle_liteetharprx_next_value_ce1 <= 1'd0;
	depacketizer_data_copy_first_liteetharprx_next_value2 <= 1'd0;
	depacketizer_data_copy_first_liteetharprx_next_value_ce2 <= 1'd0;
	liteetharpdepacketizer_next_state <= liteetharpdepacketizer_state;
	case (liteetharpdepacketizer_state)
		1'd1: begin
			depacketizer_sink_ready <= 1'd1;
			if (depacketizer_sink_valid) begin
				depacketizer_count_liteetharprx_next_value0 <= (depacketizer_count + 1'd1);
				depacketizer_count_liteetharprx_next_value_ce0 <= 1'd1;
				depacketizer_sr_shift <= 1'd1;
				if ((depacketizer_count == 5'd27)) begin
					depacketizer_data_copy_first_liteetharprx_next_value2 <= 1'd1;
					depacketizer_data_copy_first_liteetharprx_next_value_ce2 <= 1'd1;
					liteetharpdepacketizer_next_state <= 2'd2;
					depacketizer_count_liteetharprx_next_value0 <= (depacketizer_count + 1'd1);
					depacketizer_count_liteetharprx_next_value_ce0 <= 1'd1;
				end
				if (depacketizer_sink_last) begin
					liteetharpdepacketizer_next_state <= 1'd0;
				end
			end
		end
		2'd2: begin
			depacketizer_source_valid <= depacketizer_sink_valid;
			depacketizer_source_first <= depacketizer_data_copy_first;
			depacketizer_source_last <= depacketizer_sink_last;
			depacketizer_sink_ready <= depacketizer_source_ready;
			depacketizer_source_payload_data <= depacketizer_sink_payload_data;
			depacketizer_source_be <= depacketizer_sink_be;
			if ((depacketizer_source_valid & depacketizer_source_ready)) begin
				depacketizer_data_copy_first_liteetharprx_next_value2 <= 1'd0;
				depacketizer_data_copy_first_liteetharprx_next_value_ce2 <= 1'd1;
				depacketizer_fsm_from_idle_liteetharprx_next_value1 <= 1'd0;
				depacketizer_fsm_from_idle_liteetharprx_next_value_ce1 <= 1'd1;
				if (depacketizer_source_last) begin
					liteetharpdepacketizer_next_state <= 1'd0;
				end
			end
		end
		default: begin
			depacketizer_sink_ready <= 1'd1;
			depacketizer_count_liteetharprx_next_value0 <= 1'd1;
			depacketizer_count_liteetharprx_next_value_ce0 <= 1'd1;
			if (depacketizer_sink_valid) begin
				depacketizer_sr_shift <= 1'd1;
				depacketizer_fsm_from_idle_liteetharprx_next_value1 <= 1'd1;
				depacketizer_fsm_from_idle_liteetharprx_next_value_ce1 <= 1'd1;
				depacketizer_data_copy_first_liteetharprx_next_value2 <= 1'd1;
				depacketizer_data_copy_first_liteetharprx_next_value_ce2 <= 1'd1;
				if (1'd0) begin
					liteetharpdepacketizer_next_state <= 2'd2;
				end else begin
					liteetharpdepacketizer_next_state <= 1'd1;
				end
				if (($signed({1'd0, depacketizer_sink_last}) & 1'sd1)) begin
					liteetharpdepacketizer_next_state <= 1'd0;
				end
			end
		end
	endcase
// synthesis translate_off
	dummy_d_1 <= dummy_s;
// synthesis translate_on
end

// synthesis translate_off
reg dummy_d_2;
// synthesis translate_on
always @(*) begin
	source_source_valid <= 1'd0;
	source_source_payload_reply <= 1'd0;
	source_source_payload_request <= 1'd0;
	depacketizer_source_ready <= 1'd0;
	fsm_next_state <= 2'd0;
	fsm_next_state <= fsm_state;
	case (fsm_state)
		1'd1: begin
			if (valid) begin
				source_source_valid <= 1'd1;
				source_source_payload_reply <= reply;
				source_source_payload_request <= request;
			end
			fsm_next_state <= 2'd2;
		end
		2'd2: begin
			depacketizer_source_ready <= 1'd1;
			if ((depacketizer_source_valid & depacketizer_source_last)) begin
				fsm_next_state <= 1'd0;
			end
		end
		default: begin
			depacketizer_source_ready <= 1'd1;
			if (depacketizer_source_valid) begin
				depacketizer_source_ready <= 1'd0;
				fsm_next_state <= 1'd1;
			end
		end
	endcase
// synthesis translate_off
	dummy_d_2 <= dummy_s;
// synthesis translate_on
end

// synthesis translate_off
reg dummy_d_3;
// synthesis translate_on
always @(*) begin
	sink_sink_valid <= 1'd0;
	next_state <= 2'd0;
	index_fsm_next_value0 <= 6'd0;
	index_fsm_next_value_ce0 <= 1'd0;
	busy_status_fsm_next_value1 <= 1'd0;
	busy_status_fsm_next_value_ce1 <= 1'd0;
	sent_status_fsm_t_next_value0 <= 32'd0;
	sent_status_fsm_t_next_value_ce0 <= 1'd0;
	wait_count_fsm_t_next_value1 <= 6'd0;
	wait_count_fsm_t_next_value_ce1 <= 1'd0;
	gap_count_fsm_f_next_value <= 2'd0;
	gap_count_fsm_f_next_value_ce <= 1'd0;
	next_state <= state;
	case (state)
		1'd1: begin
			sink_sink_valid <= 1'd1;
			if (sink_sink_ready) begin
				if (sink_sink_last) begin
					sent_status_fsm_t_next_value0 <= (sent + 1'd1);
					sent_status_fsm_t_next_value_ce0 <= 1'd1;
					wait_count_fsm_t_next_value1 <= 5'd31;
					wait_count_fsm_t_next_value_ce1 <= 1'd1;
					next_state <= 2'd3;
				end else begin
					index_fsm_next_value0 <= (index + 1'd1);
					index_fsm_next_value_ce0 <= 1'd1;
					gap_count_fsm_f_next_value <= gap;
					gap_count_fsm_f_next_value_ce <= 1'd1;
					if ((gap != 1'd0)) begin
						next_state <= 2'd2;
					end
				end
			end
		end
		2'd2: begin
			gap_count_fsm_f_next_value <= (gap_count - 1'd1);
			gap_count_fsm_f_next_value_ce <= 1'd1;
			if ((gap_count == 1'd1)) begin
				next_state <= 1'd1;
			end
		end
		2'd3: begin
			wait_count_fsm_t_next_value1 <= (wait_count - 1'd1);
			wait_count_fsm_t_next_value_ce1 <= 1'd1;
			if ((wait_count == 1'd0)) begin
				busy_status_fsm_next_value1 <= 1'd0;
				busy_status_fsm_next_value_ce1 <= 1'd1;
				next_state <= 1'd0;
			end
		end
		default: begin
			if (run) begin
				index_fsm_next_value0 <= 1'd0;
				index_fsm_next_value_ce0 <= 1'd1;
				busy_status_fsm_next_value1 <= 1'd1;
				busy_status_fsm_next_value_ce1 <= 1'd1;
				next_state <= 1'd1;
			end
		end
	endcase
// synthesis translate_off
	dummy_d_3 <= dummy_s;
// synthesis translate_on
end
assign slice_proxy0 = depacketizer_header[39:32];
assign slice_proxy1 = depacketizer_header[15:0];
assign slice_proxy2 = depacketizer_header[15:0];
assign slice_proxy3 = depacketizer_header[63:48];
assign slice_proxy4 = depacketizer_header[63:48];
assign slice_proxy5 = depacketizer_header[31:16];
assign slice_proxy6 = depacketizer_header[31:16];
assign slice_proxy7 = depacketizer_header[47:40];
assign slice_proxy8 = depacketizer_header[143:112];
assign slice_proxy9 = depacketizer_header[143:112];
assign slice_proxy10 = depacketizer_header[143:112];
assign slice_proxy11 = depacketizer_header[143:112];
assign slice_proxy12 = depacketizer_header[111:64];
assign slice_proxy13 = depacketizer_header[111:64];
assign slice_proxy14 = depacketizer_header[111:64];
assign slice_proxy15 = depacketizer_header[111:64];
assign slice_proxy16 = depacketizer_header[111:64];
assign slice_proxy17 = depacketizer_header[111:64];
assign slice_proxy18 = depacketizer_header[223:192];
assign slice_proxy19 = depacketizer_header[223:192];
assign slice_proxy20 = depacketizer_header[223:192];
assign slice_proxy21 = depacketizer_header[223:192];
assign slice_proxy22 = depacketizer_header[191:144];
assign slice_proxy23 = depacketizer_header[191:144];
assign slice_proxy24 = depacketizer_header[191:144];
assign slice_proxy25 = depacketizer_header[191:144];
assign slice_proxy26 = depacketizer_header[191:144];
assign slice_proxy27 = depacketizer_header[191:144];

// synthesis translate_off
reg dummy_d_4;
// synthesis translate_on
always @(*) begin
	self <= 8'd0;
	case (index)
		1'd0: begin
			self <= 8'd0;
		end
		1'd1: begin
			self <= 8'd1;
		end
		2'd2: begin
			self <= 8'd8;
		end
		2'd3: begin
			self <= 8'd0;
		end
		3'd4: begin
			self <= 8'd6;
		end
		3'd5: begin
			self <= 8'd4;
		end
		3'd6: begin
			self <= 8'd0;
		end
		3'd7: begin
			self <= 8'd2;
		end
		4'd8: begin
			self <= 8'd108;
		end
		4'd9: begin
			self <= 8'd43;
		end
		4'd10: begin
			self <= 8'd89;
		end
		4'd11: begin
			self <= 8'd244;
		end
		4'd12: begin
			self <= 8'd118;
		end
		4'd13: begin
			self <= 8'd232;
		end
		4'd14: begin
			self <= 8'd192;
		end
		4'd15: begin
			self <= 8'd168;
		end
		5'd16: begin
			self <= 8'd2;
		end
		5'd17: begin
			self <= 8'd107;
		end
		5'd18: begin
			self <= 8'd2;
		end
		5'd19: begin
			self <= 8'd192;
		end
		5'd20: begin
			self <= 8'd222;
		end
		5'd21: begin
			self <= 8'd112;
		end
		5'd22: begin
			self <= 8'd96;
		end
		5'd23: begin
			self <= 8'd1;
		end
		5'd24: begin
			self <= 8'd192;
		end
		5'd25: begin
			self <= 8'd168;
		end
		5'd26: begin
			self <= 8'd2;
		end
		5'd27: begin
			self <= 8'd206;
		end
		5'd28: begin
			self <= 8'd0;
		end
		5'd29: begin
			self <= 8'd0;
		end
		5'd30: begin
			self <= 8'd0;
		end
		5'd31: begin
			self <= 8'd0;
		end
		6'd32: begin
			self <= 8'd0;
		end
		6'd33: begin
			self <= 8'd0;
		end
		6'd34: begin
			self <= 8'd0;
		end
		6'd35: begin
			self <= 8'd0;
		end
		6'd36: begin
			self <= 8'd0;
		end
		6'd37: begin
			self <= 8'd0;
		end
		6'd38: begin
			self <= 8'd0;
		end
		6'd39: begin
			self <= 8'd0;
		end
		6'd40: begin
			self <= 8'd0;
		end
		6'd41: begin
			self <= 8'd0;
		end
		6'd42: begin
			self <= 8'd0;
		end
		6'd43: begin
			self <= 8'd0;
		end
		6'd44: begin
			self <= 8'd0;
		end
		default: begin
			self <= 8'd0;
		end
	endcase
// synthesis translate_off
	dummy_d_4 <= dummy_s;
// synthesis translate_on
end

always @(posedge sys_clk) begin
	if ((source_source_valid & source_source_ready)) begin
		received <= (received + 1'd1);
		last_ip <= source_source_payload_ip_address;
		last_mac_lo <= source_source_payload_mac_address[31:0];
		last_mac_hi <= source_source_payload_mac_address[47:32];
		if (((((~source_source_payload_reply) | source_source_payload_request) | (source_source_payload_ip_address != 32'd3232236139)) | (source_source_payload_mac_address != 47'd118933448586984))) begin
			errors <= (errors + 1'd1);
		end
	end
	valid <= (((((depacketizer_source_valid & (depacketizer_source_param_hwtype == 1'd1)) & (depacketizer_source_param_proto == 12'd2048)) & (depacketizer_source_param_hwsize == 3'd6)) & (depacketizer_source_param_protosize == 3'd4)) & (depacketizer_source_param_target_ip == 32'd3232236238));
	if (depacketizer_sr_shift) begin
		depacketizer_sr <= {depacketizer_sink_payload_data, depacketizer_sr[223:8]};
	end
	if (depacketizer_sr_shift_leftover) begin
		depacketizer_sr <= {depacketizer_sink_payload_data, depacketizer_sr[223:0]};
	end
	liteetharpdepacketizer_state <= liteetharpdepacketizer_next_state;
	if (depacketizer_count_liteetharprx_next_value_ce0) begin
		depacketizer_count <= depacketizer_count_liteetharprx_next_value0;
	end
	if (depacketizer_fsm_from_idle_liteetharprx_next_value_ce1) begin
		depacketizer_fsm_from_idle <= depacketizer_fsm_from_idle_liteetharprx_next_value1;
	end
	if (depacketizer_data_copy_first_liteetharprx_next_value_ce2) begin
		depacketizer_data_copy_first <= depacketizer_data_copy_first_liteetharprx_next_value2;
	end
	fsm_state <= fsm_next_state;
	state <= next_state;
	if (index_fsm_next_value_ce0) begin
		index <= index_fsm_next_value0;
	end
	if (busy_status_fsm_next_value_ce1) begin
		busy <= busy_status_fsm_next_value1;
	end
	if (sent_status_fsm_t_next_value_ce0) begin
		sent <= sent_status_fsm_t_next_value0;
	end
	if (wait_count_fsm_t_next_value_ce1) begin
		wait_count <= wait_count_fsm_t_next_value1;
	end
	if (gap_count_fsm_f_next_value_ce) begin
		gap_count <= gap_count_fsm_f_next_value;
	end
	if (sys_rst) begin
		busy <= 1'd0;
		sent <= 32'd0;
		received <= 32'd0;
		errors <= 32'd0;
		last_ip <= 32'd0;
		last_mac_lo <= 32'd0;
		last_mac_hi <= 16'd0;
		depacketizer_count <= 5'd0;
		depacketizer_data_copy_first <= 1'd0;
		depacketizer_fsm_from_idle <= 1'd0;
		index <= 6'd0;
		gap_count <= 2'd0;
		wait_count <= 6'd0;
		liteetharpdepacketizer_state <= 2'd0;
		fsm_state <= 2'd0;
		state <= 2'd0;
	end
end

endmodule

