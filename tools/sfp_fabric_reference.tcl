# Optional model-only experiment. Never program its bitstream on ZC706.
set source_dir [file normalize [lindex $argv 0]]
set output_dir [file normalize [lindex $argv 1]]
file mkdir $output_dir
set_param general.maxThreads 2
cd $source_dir
read_verilog top.v
synth_design -top top -part xc7z030fbg676-2 -flatten_hierarchy none
read_xdc top.xdc
create_clock -name si_input -period 10 [get_ports mgt_refclk_p]
opt_design
# GTGREFCLK is intentionally used for this test-only model.
set_property SEVERITY Warning [get_drc_checks REQP-52]
place_design
route_design
report_drc -file [file join $output_dir drc.rpt]
report_timing_summary -file [file join $output_dir timing.rpt]
set report [open [file join $output_dir reference-routing.txt] w]
foreach cell [get_cells -hierarchical -filter {REF_NAME == GTXE2_CHANNEL}] {
    foreach pin [get_pins -of_objects $cell -filter {REF_PIN_NAME == GTGREFCLK || REF_PIN_NAME == GTREFCLK1}] {
        foreach net [get_nets -of_objects $pin] {
            if {![string match "<const*>" $net]} {
                puts $report "PIN $pin NET $net ROUTE [get_property ROUTE $net]"
            }
        }
    }
}
close $report
write_checkpoint -force [file join $output_dir routed.dcp]
# Unassigned pads are acceptable only for this model, never for hardware.
set_property SEVERITY Warning [get_drc_checks UCIO-1]
write_bitstream -force [file join $output_dir model-only.bit]
exit
