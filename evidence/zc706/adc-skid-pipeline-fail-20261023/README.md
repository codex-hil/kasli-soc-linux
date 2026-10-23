# First pipeline implementation failed setup

SYS75.91/83.33MHz, final hold0. Critical path moved to ADC1 command-pipeline
PipeReady skid data register bit261 CE. This CE drives537 cells; total13.17ns,
11.30ns routing. The address pipeline exists and RTL passes, but delayed DDR
ready now feeds a high-fanout skid capture enable. No admission/programming.
Full log retained on Dell under build/zc706-integrated-network-reset-pipeline-20261023/gateware/gateware/stage1.log;
SHA and critical extract included. Next replace wide skid capture with local
occupancy queue rather than register ready alone or ignore timing.
