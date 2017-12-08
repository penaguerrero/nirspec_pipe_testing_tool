
"""
py.test module for unit testing the bkg_subtract step.
"""

import pytest
import os
from jwst.background.background_step import BackgroundStep

from .. import core_utils
from . import bkg_subtract_utils


# Set up the fixtures needed for all of the tests, i.e. open up all of the FITS files

# Default names of pipeline input and output files
@pytest.fixture(scope="module")
def set_inandout_filenames(request, config):
    step = "bkg_subtract"
    step_info = core_utils.set_inandout_filenames(step, config)
    step_input_filename, step_output_filename, in_file_suffix, out_file_suffix, True_steps_suffix_map = step_info
    return step, step_input_filename, step_output_filename, in_file_suffix, out_file_suffix, True_steps_suffix_map


# fixture to read the output file header
@pytest.fixture(scope="module")
def output_hdul(set_inandout_filenames, config):
    set_inandout_filenames_info = core_utils.read_info4outputhdul(config, set_inandout_filenames)
    step, txt_name, step_input_file, step_output_file, run_calwebb_spec2, outstep_file_suffix = set_inandout_filenames_info
    stp = BackgroundStep()
    skip_runing_pipe_step = config.getboolean("tests_only", "_".join((step, "tests")))
    # if run_calwebb_spec2 is True calwebb_spec2 will be called, else individual steps will be ran
    step_completed = False
    if config.getboolean("steps", step):
        print ("*** Step "+step+" set to True")
        if os.path.isfile(step_input_file):
            print(" The input file ", step_input_file,"exists... will run step "+step)
            bkg_list = core_utils.getlist("additional_arguments", "bkg_list")
            existing_bgfiles = 0
            for bg_file in bkg_list:
                if os.path.isfile(bg_file):
                    existing_bgfiles += 1
            if existing_bgfiles == 0:
                print (" Need at least one background file to continue. Step will be skipped.")
                core_utils.add_completed_steps(txt_name, step, outstep_file_suffix, step_completed)
                pytest.skip("Skipping "+step+" because files listed on bkg_list in the configuration file do not exist.")
            else:
                if not skip_runing_pipe_step:
                    result = stp.call(step_input_file, bkg_list)
                    if result is not None:
                        result.save(step_output_file)
                        hdul = core_utils.read_hdrfits(step_output_file, info=False, show_hdr=False)
                        step_completed = True
                    else:
                        hdul = core_utils.read_hdrfits(step_input_file, info=False, show_hdr=False)
                else:
                    hdul = core_utils.read_hdrfits(step_output_file, info=False, show_hdr=False)
                    step_completed = True
                core_utils.add_completed_steps(txt_name, step, outstep_file_suffix, step_completed)
                return hdul
        else:
            print (" The input file does not exist. Skipping step.")
            core_utils.add_completed_steps(txt_name, step, outstep_file_suffix, step_completed)
            pytest.skip("Skipping "+step+" because the input file does not exist.")
    else:
        core_utils.add_completed_steps(txt_name, step, outstep_file_suffix, step_completed)
        pytest.skip("Skipping "+step+". Step set to False in configuration file.")



# Unit tests

def test_s_bkdsub_exists(output_hdul):
    assert bkg_subtract_utils.s_bkdsub_exists(output_hdul), "The keyword S_BKDSUB was not added to the header --> background step was not completed."
