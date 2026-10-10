# Optional debug comparator only. The normal openXC7 build never calls this.
# vivado -mode batch -source tools/sfp_vivado_reference.tcl \
#   -tclargs build/zc706-sfp/gateware/gateware build/zc706-sfp/vivado-reference
if {$argc != 2} {
    error "Expected generated gateware directory and separate reference output directory"
}
set source_dir [file normalize [lindex $argv 0]]
set output_dir [file normalize [lindex $argv 1]]
set device xc7z045ffg900-2
if {[llength [get_parts -quiet $device]] != 1} {
    error "ZC706 Zynq-7000 part support is absent from this optional Vivado installation"
}
if {$source_dir eq $output_dir} {
    error "Reference output must be separate from the open-source build"
}
foreach name {top.v top.xdc} {
    if {![file isfile [file join $source_dir $name]]} {
        error "Missing generated $name"
    }
}
file mkdir $output_dir
set_param general.maxThreads 2
cd $source_dir
read_verilog top.v
synth_design -top top -part $device -flatten_hierarchy none
read_xdc top.xdc
write_checkpoint -force [file join $output_dir synthesized.dcp]
opt_design
place_design
phys_opt_design
route_design
report_drc -file [file join $output_dir drc.rpt]
report_timing_summary -file [file join $output_dir timing.rpt]
write_checkpoint -force [file join $output_dir routed.dcp]
write_bitstream -force [file join $output_dir reference.bit]
exit
