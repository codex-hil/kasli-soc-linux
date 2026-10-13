/* Included only in a build-local liblitedram diagnostic copy. */
extern int sdram_lab_timed_out(void);
int sdram_lab_dqs_sweep(int sweep_dq) {
    unsigned tested = 0, best_errors = ~0U;
    int result = 0;
    sdram_software_control_on();
    if (sweep_dq == 3) {
        sdram_leveling_action(4, 0, write_rst_dq_delay);
        sdram_leveling_action(4, 0, write_rst_dqs_delay);
        sdram_leveling_action(4, 0, write_inc_dqs_delay);
        sdram_leveling_action(4, 0, read_rst_dq_bitslip);
        printf("DQ_EYE settings dq_offset=0 dqs_offset=1 repeats=4 seeds=3\n");
        sdram_lab_detail_active = 2;
        unsigned passing = 0;
        for (unsigned slip=0;slip<8;slip++) {
            sdram_leveling_action(4, 0, read_rst_dq_delay);
            for (unsigned delay=0;delay<32;delay++) {
                if (sdram_lab_timed_out()) { result=-1; goto eye_done; }
                for (unsigned bit=0;bit<8;bit++) sdram_lab_bit_errors[bit]=0;
                sdram_lab_samples=0;
                unsigned errors=0;
                for (unsigned repeat=0;repeat<4;repeat++) errors += run_test_pattern(4,0);
                tested += 12;
                if (errors < best_errors) best_errors = errors;
                passing += errors == 0;
                printf("DQ_EYE slip=%u delay=%u samples=%u errors=",slip,delay,sdram_lab_samples);
                for (unsigned bit=0;bit<8;bit++) printf("%s%u",bit ? "," : "",sdram_lab_bit_errors[bit]);
                printf("\n");
                sdram_leveling_action(4,0,read_inc_dq_delay);
            }
            sdram_leveling_action(4,0,read_inc_dq_bitslip);
        }
        result = passing ? 1 : 0;
eye_done:
        sdram_lab_detail_active=0;
        printf("DQ_EYE complete=%d passing_settings=%u tested=%u (diagnostic only)\n",result!=-1,passing,tested);
        goto done;
    }
    if (sweep_dq == 2) {
        sdram_leveling_action(4, 0, write_rst_dq_delay);
        sdram_leveling_action(4, 0, write_rst_dqs_delay);
        sdram_leveling_action(4, 0, write_inc_dqs_delay);
        sdram_leveling_action(4, 0, read_rst_dq_bitslip);
        for (unsigned i=0;i<4;i++) sdram_leveling_action(4, 0, read_inc_dq_bitslip);
        sdram_leveling_action(4, 0, read_rst_dq_delay);
        for (unsigned i=0;i<13;i++) sdram_leveling_action(4, 0, read_inc_dq_delay);
        printf("DQ_DETAIL settings dq_offset=0 dqs_offset=1 read_slip_offset=4 read_delay=13 repeats=16 seeds=3\n");
        sdram_lab_detail_active = 1;
        unsigned total_errors = 0;
        for (unsigned repeat=0;repeat<16;repeat++) {
            if (sdram_lab_timed_out()) { result = -1; break; }
            total_errors += run_test_pattern(4, 0);
            tested += 3;
        }
        sdram_lab_detail_active = 0;
        best_errors = total_errors;
        if (result != -1) result = total_errors == 0 ? 1 : 0;
        goto done;
    }
    if (sweep_dq) sdram_leveling_action(4, 0, write_rst_dq_delay);
    for (unsigned dq = 0; dq < (sweep_dq ? 32U : 1U); dq++) {
        sdram_leveling_action(4, 0, write_rst_dqs_delay);
        for (unsigned dqs = 0; dqs < 32; dqs++) {
            sdram_leveling_action(4, 0, read_rst_dq_bitslip);
            for (unsigned slip = 0; slip < 8; slip++) {
                sdram_leveling_action(4, 0, read_rst_dq_delay);
                for (unsigned delay = 0; delay < 32; delay++) {
                    if (sdram_lab_timed_out()) { result = -1; goto done; }
                    unsigned errors = run_test_pattern_seeds(4, 0, 1);
                    tested++;
                    if (errors < best_errors) {
                        best_errors = errors;
                        printf("DQS_SWEEP best dq_offset=%u dqs_offset=%u read_slip_offset=%u read_delay=%u errors=%u tested=%u\n",
                            dq,dqs,slip,delay,errors,tested);
                    }
                    if (!errors && !run_test_pattern(4, 0)) {
                        printf("DQS_SWEEP candidate dq_offset=%u dqs_offset=%u read_slip_offset=%u read_delay=%u seeds=3 tested=%u\n",
                            dq, dqs, slip, delay, tested);
                        result = 1;
                        goto done;
                    }
                    sdram_leveling_action(4, 0, read_inc_dq_delay);
                }
                sdram_leveling_action(4, 0, read_inc_dq_bitslip);
            }
            printf("DQS_SWEEP progress dq_offset=%u dqs_offset=%u tested=%u best_errors=%u\n",dq,dqs,tested,best_errors);
            sdram_leveling_action(4, 0, write_inc_dqs_delay);
        }
        if (sweep_dq) sdram_leveling_action(4, 0, write_inc_dq_delay);
    }
done:
    sdram_software_control_off();
    printf("DQS_SWEEP result=%d tested=%u best_errors=%u (diagnostic only; does not qualify DDR)\n",
        result,tested,best_errors);
    return result;
}
