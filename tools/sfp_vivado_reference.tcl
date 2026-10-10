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
# nextpnr's XDC reader accepts internal nets in get_ports clock commands.
# Vivado distinguishes ports and nets; retain pad constraints unchanged.
set constraints [open top.xdc r]
set xdc [read $constraints]
close $constraints
set converted {}
foreach line [split $xdc "\n"] {
    if {[string match "create_clock *" $line]} {
        set line [string map {{get_ports } {get_nets }} $line]
    }
    lappend converted $line
}
set constraints [open [file join $output_dir reference.xdc] w]
puts $constraints [join $converted "\n"]
close $constraints
read_xdc [file join $output_dir reference.xdc]
create_clock -name si5324_input -period 8.0 [get_ports mgt_refclk_p]
write_checkpoint -force [file join $output_dir synthesized.dcp]
opt_design
place_design
phys_opt_design
route_design
set reference_report [open [file join $output_dir reference-routing.txt] w]
foreach cell [get_cells -hierarchical -filter {REF_NAME == IBUFDS_GTE2 || REF_NAME == GTXE2_CHANNEL}] {
    puts $reference_report "CELL $cell LOC=[get_property LOC $cell]"
    foreach pin [get_pins -of_objects $cell -filter {REF_PIN_NAME == GTNORTHREFCLK1 || REF_PIN_NAME == GTREFCLKMONITOR || REF_PIN_NAME == O || REF_PIN_NAME == ODIV2}] {
        foreach net [get_nets -of_objects $pin] {
            puts $reference_report "PIN $pin NET $net ROUTE [get_property ROUTE $net]"
        }
    }
}
close $reference_report
report_drc -file [file join $output_dir drc.rpt]
report_timing_summary -file [file join $output_dir timing.rpt]
write_checkpoint -force [file join $output_dir routed.dcp]
write_bitstream -force [file join $output_dir reference.bit]
exit
