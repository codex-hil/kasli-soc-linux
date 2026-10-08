# Two-card ADC target: J5 LPC + J4 HPC, VADJ 2.5 V required.
# Independent clocks and snapshots; no inter-card synchronization.
# Optional SD script; no saveenv/QSPI writes. Keep the original boot.scr.
# Fail closed if the FPGA cannot be programmed: Linux CSR access needs this PL.
if load mmc 0:1 ${kernel_addr_r} adc-dual.bit; then
    if fpga loadb 0 ${kernel_addr_r} ${filesize}; then
        # Same post-configuration PS sequence as the validated JTAG loader:
        # enable PS/PL level shifters, release PL reset, FCLK0 = 100 MHz.
        mw.l 0xf8000008 0xdf0d
        mw.l 0xf8000900 0xf
        mw.l 0xf8000240 0xf
        mw.l 0xf8000240 0
        mw.l 0xf8000170 0x00100a00
        if load mmc 0:1 ${fdt_addr_r} zc706.dtb; then
            if load mmc 0:1 ${kernel_addr_r} zImage; then
                setenv bootargs console=ttyPS0,115200 root=/dev/mmcblk0p2 rootwait rw clk_ignore_unused uio_pdrv_genirq.of_id=generic-uio
                bootz ${kernel_addr_r} - ${fdt_addr_r}
            fi
        fi
    fi
fi
echo SD boot failed; reset or inspect the serial console
