module top(input i, t, output o, inout pad);
IOBUF io(.I(i),.T(t),.O(o),.IO(pad));
endmodule
