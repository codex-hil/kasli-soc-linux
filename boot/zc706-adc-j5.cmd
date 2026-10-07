# One-card ADC test: verified VADJ 2.5 V, card in J5 LPC.
# Optional SD script; no saveenv/QSPI writes. Keep the original boot.scr.
# Fail closed if the FPGA cannot be programmed: Linux CSR access needs this PL.
if load mmc 0:1 ${kernel_addr_r} adc-j5.bit; then
    if fpga loadb 0 ${kernel_addr_r} ${filesize}; then
        if load mmc 0:1 ${fdt_addr_r} zc706.dtb; then
            if load mmc 0:1 ${kernel_addr_r} zImage; then
                setenv bootargs console=ttyPS0,115200 root=/dev/mmcblk0p2 rootwait rw clk_ignore_unused uio_pdrv_genirq.of_id=generic-uio
                bootz ${kernel_addr_r} - ${fdt_addr_r}
            fi
        fi
    fi
fi
echo SD boot failed; reset or inspect the serial console
