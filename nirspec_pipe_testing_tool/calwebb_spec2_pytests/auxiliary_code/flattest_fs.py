import time
import os
import numpy as np
from astropy.io import fits

from gwcs import wcstools
from jwst import datamodels

from . import auxiliary_functions as auxfunc

"""
This script tests the pipeline flat field step output for MOS data. It is the python version of the IDL script
(with the same name) written by James Muzerolle.
"""

# HEADER
__author__ = "M. A. Pena-Guerrero"
__version__ = "2.6"


# HISTORY
# Nov 2017 - Version 1.0: initial version completed
# May 2018 - Version 2.0: Completely changed script to use the datamodel instead of the compute_world_coordinates
#                         script, and added new routines for statistics calculations.
# Jun 2018 - Version 2.1: Changed extension numbers for the name of the extension in the D-, F-, and S-flats.
# Jun 2018 - Version 2.2: Removed function reverse_cols because it was not behaving as expected.
# Apr 2019 - Version 2.3: Implemented logging capability.
# May 2019 - Version 2.4: Implemented images of the residuals.
# Jun 2019 - Version 2.5: Updated name of interpolated flat to be the default pipeline name for this file.
# Sept 2019 - Version 2.6: Updated line to call model for SlitModel to work correctly with pipeline changes.


def flattest(step_input_filename, dflatref_path, sfile_path, fflat_path, writefile=True,
             show_figs=True, save_figs=False, plot_name=None, threshold_diff=1.0e-7, debug=False):
    """
    This function calculates the difference between the pipeline and the calculated flat field values.
    The functions uses the output of the compute_world_coordinates.py script.

    Args:
        step_input_filename: str, name of the output fits file from the 2d_extract step (with full path)
        dflatref_path: str, path of where the D-flat reference fits files
        sfile_path: str, path of where the S-flat reference fits files
        fflat_path: str, path of where the F-flat reference fits files
        writefile: boolean, if True writes the fits files of the calculated flat and difference images
        show_figs: boolean, whether to show plots or not
        save_figs: boolean, save the plots (the 3 plots can be saved or not independently with the function call)
        plot_name: string, desired name (if name is not given, the plot function will name the plot by
                    default)
        threshold_diff: float, threshold difference between pipeline output and ESA file
        debug: boolean, if true a series of print statements will show on-screen

    Returns:
        - 1 plot, if told to save and/or show them.
        - median_diff: Boolean, True if smaller or equal to threshold.
        - log_msgs: list, all print statements are captured in this variable

    """

    log_msgs = []

    # start the timer
    flattest_start_time = time.time()

    # get info from the rate file header
    det = fits.getval(step_input_filename, "DETECTOR", 0)
    msg = 'step_input_filename=' + step_input_filename
    print(msg)
    log_msgs.append(msg)
    exptype = fits.getval(step_input_filename, "EXP_TYPE", 0)
    grat = fits.getval(step_input_filename, "GRATING", 0)
    filt = fits.getval(step_input_filename, "FILTER", 0)
    msg = "flat_field_file  -->     Grating:" + grat + "   Filter:" + filt + "   EXP_TYPE:" + exptype
    print(msg)
    log_msgs.append(msg)

    # read in the on-the-fly flat image
    flatfile = step_input_filename.replace("flat_field.fits", "interpolatedflat.fits")
    # flatfile = step_input_filename.replace("flat_field.fits", "intflat.fits")  # for testing code only!

    # get the reference files
    # D-Flat
    if ".fits" not in dflatref_path:
        dflat_ending = "f_01.03.fits"
        t = (dflatref_path, "nrs1", dflat_ending)
        dfile = "_".join(t)
        if det == "NRS2":
            dfile = dfile.replace("nrs1", "nrs2")
    else:
        dfile = dflatref_path
    msg = "Using D-flat: " + dfile
    print(msg)
    log_msgs.append(msg)
    dfim = fits.getdata(dfile, "SCI")
    dfimdq = fits.getdata(dfile, "DQ")
    # need to flip/rotate the image into science orientation
    ns = np.shape(dfim)
    dfim = np.transpose(dfim, (0, 2, 1))  # keep in mind that 0,1,2 = z,y,x in Python, whereas =x,y,z in IDL
    dfimdq = np.transpose(dfimdq)
    if det == "NRS2":
        # rotate science data by 180 degrees for NRS2
        dfim = dfim[..., ::-1, ::-1]
        dfimdq = dfimdq[..., ::-1, ::-1]
    naxis3 = fits.getval(dfile, "NAXIS3", 1)
    if debug:
        print('np.shape(dfim) =', np.shape(dfim))
        print('np.shape(dfimdq) =', np.shape(dfimdq))

    # get the wavelength values
    dfwave = np.array([])
    for i in range(naxis3):
        t = ("PFLAT", str(i + 1))
        keyword = "_".join(t)
        dfwave = np.append(dfwave, fits.getval(dfile, keyword, 1))
    dfrqe = fits.getdata(dfile, 2)

    # S-flat
    mode = "FS"
    if filt == "F070LP":
        flat = "FLAT4"
    elif filt == "F100LP":
        flat = "FLAT1"
    elif filt == "F170LP":
        flat = "FLAT2"
    elif filt == "F290LP":
        flat = "FLAT3"
    elif filt == "CLEAR":
        flat = "FLAT5"
    else:
        msg = "No filter correspondence. Exiting the program."
        print(msg)
        log_msgs.append(msg)
        result_msg = "Test skiped because there is no flat correspondence for the filter in the data: {}".format(filt)
        median_diff = "skip"
        return median_diff, result_msg, log_msgs

    if ".fits" not in sfile_path:
        sflat_ending = "f_01.01.fits"
        t = (sfile_path, grat, "OPAQUE", flat, "nrs1", sflat_ending)
        sfile = "_".join(t)
        if det == "NRS2":
            sfile = sfile.replace("nrs1", "nrs2")
    else:
        sfile = sfile_path

    if mode not in sfile_path:
        msg = "Wrong path in for mode S-flat. This script handles mode " + mode + "only."
        print(msg)
        log_msgs.append(msg)
        # This is the key argument for the assert pytest function
        result_msg = "Wrong path in for mode S-flat. Test skiped because mode is not FS."
        median_diff = "skip"
        return median_diff, result_msg, log_msgs

    if debug:
        print("grat = ", grat)
        print("flat = ", flat)
        print("sfile used = ", sfile)

    msg = "Using S-flat: " + sfile
    print(msg)
    log_msgs.append(msg)
    sfim = fits.getdata(sfile, "SCI")  # 1)
    sfimdq = fits.getdata(sfile, "DQ")  # 3)

    # need to flip/rotate image into science orientation
    sfim = np.transpose(sfim)
    sfimdq = np.transpose(sfimdq)
    if det == "NRS2":
        # rotate science data by 180 degrees for NRS2
        sfim = sfim[..., ::-1, ::-1]
        sfimdq = sfimdq[..., ::-1, ::-1]
    if debug:
        print("np.shape(sfim) = ", np.shape(sfim))
        print("np.shape(sfimdq) = ", np.shape(sfimdq))
        sf = fits.open(sfile)
        print(sf.info())
    try:
        sfv_a2001 = fits.getdata(sfile, "SLIT_A_200_1")
        sfv_a2002 = fits.getdata(sfile, "SLIT_A_200_2")
        sfv_a400 = fits.getdata(sfile, "SLIT_A_400")
        sfv_a1600 = fits.getdata(sfile, "SLIT_A_1600")
    except KeyError:
        print(" * S-Flat-Field file does not have extensions for slits 200A1, 200A2, 400A, or 1600A, trying with 200B")
    if det == "NRS2":
        sfv_b200 = fits.getdata(sfile, "SLIT_B_200")

    # F-Flat
    if ".fits" not in fflat_path:
        fflat_ending = "01.01.fits"
        ffile = "_".join((fflat_path, filt, fflat_ending))
    else:
        ffile = fflat_path

    if mode not in fflat_path:
        msg = "Wrong path in for mode F-flat. This script handles mode " + mode + "only."
        print(msg)
        log_msgs.append(msg)
        # This is the key argument for the assert pytest function
        median_diff = "skip"
        return median_diff, msg, log_msgs

    msg = "Using F-flat: " + ffile
    print(msg)
    log_msgs.append(msg)
    ffv = fits.getdata(ffile, 1)

    # now go through each pixel in the test data

    # get the datamodel from the assign_wcs output file
    extract2d_wcs_file = step_input_filename.replace("_flat_field.fits", "_extract_2d.fits")
    model = datamodels.MultiSlitModel(extract2d_wcs_file)

    if writefile:
        # create the fits list to hold the calculated flat values for each slit
        hdu0 = fits.PrimaryHDU()
        outfile = fits.HDUList()
        outfile.append(hdu0)

        # create the fits list to hold the image of pipeline-calculated difference values
        hdu0 = fits.PrimaryHDU()
        complfile = fits.HDUList()
        complfile.append(hdu0)

    # list to determine if pytest is passed or not
    total_test_result = []

    # loop over the slits
    sltname_list = ["S200A1", "S200A2", "S400A1", "S1600A1"]
    msg = "Now looping through the slits. This may take a while... "
    print(msg)
    log_msgs.append(msg)
    if det == "NRS2":
        sltname_list.append("S200B1")

    # but check if data is BOTS
    if fits.getval(step_input_filename, "EXP_TYPE", 0) == "NRS_BRIGHTOBJ":
        sltname_list = ["S1600A1"]

    # get all the science extensions
    sci_ext_list = auxfunc.get_sci_extensions(flatfile)

    # do the loop over the slits
    for slit_id in sltname_list:
        continue_flat_field_test = False
        if fits.getval(step_input_filename, "EXP_TYPE", 0) == "NRS_BRIGHTOBJ":
            slit = model
            continue_flat_field_test = True
        else:
            for slit_in_MultiSlitModel in model.slits:
                if slit_in_MultiSlitModel.name == slit_id:
                    slit = slit_in_MultiSlitModel
                    continue_flat_field_test = True
                    break

        if not continue_flat_field_test:
            continue
        else:
            # select the appropriate S-flat fast vector
            if slit_id == "S200A1":
                sfv = sfv_a2001
            if slit_id == "S200A2":
                sfv = sfv_a2002
            if slit_id == "S400A1":
                sfv = sfv_a400
            if slit_id == "S1600A1":
                sfv = sfv_a1600
            if slit_id == "S200B1":
                sfv = sfv_b200

            msg = "\nWorking with slit: " + slit_id
            print(msg)
            log_msgs.append(msg)
            try:
                ext = sci_ext_list[slit_id]  # this is for getting the science extension in the pipeline calculated flat
            except KeyError:
                # the extension does not exist in the file, look for the next slit name
                #ext = sltname_list.index(slit_id)
                continue

            # get the wavelength
            # slit.x(y)start are 1-based, turn them to 0-based for extraction
            # xstart, xend = slit.xstart - 1, slit.xstart -1 + slit.xsize
            # ystart, yend = slit.ystart - 1, slit.ystart -1 + slit.ysize
            # y, x = np.mgrid[ystart: yend, xstart: xend]
            x, y = wcstools.grid_from_bounding_box(slit.meta.wcs.bounding_box, step=(1, 1), center=True)
            ra, dec, wave = slit.meta.wcs(x, y)  # wave is in microns
            # detector2slit = slit.meta.wcs.get_transform('detector', 'slit_frame')
            # sx, sy, ls = detector2slit(x, y)
            # world_coordinates = np.array([wave, ra, dec, sy])#, x, y])

            # msg = "wavelength array: "+repr(wave[19, 483])
            # print(msg)
            # log_msgs.append(msg)

            # get the subwindow origin
            px0 = slit.xstart - 1 + model.meta.subarray.xstart
            py0 = slit.ystart - 1 + model.meta.subarray.ystart
            msg = " Subwindow origin:   px0=" + repr(px0) + "   py0=" + repr(py0)
            print(msg)
            log_msgs.append(msg)
            n_p = np.shape(wave)
            nw = n_p[0] * n_p[1]
            nw1, nw2 = n_p[1], n_p[0]  # remember that x=nw1 and y=nw2 are reversed  in Python
            if debug:
                print(" nw1, nw2, nw = ", nw1, nw2, nw)

            delf = np.zeros([nw2, nw1]) + 999.0
            flatcor = np.zeros([nw2, nw1]) + 999.0

            # read the pipeline-calculated flat image
            # there are four extensions in the flatfile: SCI, DQ, ERR, WAVELENGTH
            pipeflat = fits.getdata(flatfile, ext)

            # make sure the two arrays are the same shape
            if np.shape(flatcor) != np.shape(pipeflat):
                msg1 = 'WARNING -> Something went wrong, arrays are not the same shape:'
                msg2 = 'np.shape(flatcor) = ' + repr(np.shape(flatcor)) + '   np.shape(pipeflat) = ' + repr(
                    np.shape(pipeflat))
                msg3 = 'Mathematical operations will fail. Exiting the loop here and setting test as FAILED.'
                print(msg1)
                print(msg2)
                print(msg3)
                log_msgs.append(msg1)
                log_msgs.append(msg2)
                log_msgs.append(msg3)
                msg = " *** Result of the test: " + test_result + "\n"
                '''
                msg = 'Forcing arrays to be the same length.'
                n_p = np.shape(pipeflat)
                delf = np.zeros(n_p) + 999.0
                flatcor = np.zeros(n_p) + 999.0
                '''
                print(msg)
                log_msgs.append(msg)
                test_result = "FAILED"
                total_test_result.append(test_result)
                continue

            # loop through the wavelengths
            msg = " Looping through the wavelengths... "
            print(msg)
            log_msgs.append(msg)
            for j in range(nw1):  # in x
                for k in range(nw2):  # in y
                    if np.isfinite(wave[k, j]):  # skip if wavelength is NaN
                        # get thr full-frame pixel indeces for D- and S-flat image components
                        pind = [k + py0 - 1, j + px0 - 1]

                        # get the pixel bandwidth
                        if (j != 0) and (j < nw1 - 1):
                            if np.isfinite(wave[k, j + 1]) and np.isfinite(wave[k, j - 1]):
                                delw = 0.5 * (wave[k, j + 1] - wave[k, j - 1])
                            if np.isfinite(wave[k, j + 1]) and not np.isfinite(wave[k, j - 1]):
                                delw = wave[k, j + 1] - wave[k, j]
                            if not np.isfinite(wave[k, j + 1]) and np.isfinite(wave[k, j - 1]):
                                delw = wave[k, j] - wave[k, j - 1]
                        if j == 0:
                            delw = wave[k, j + 1] - wave[k, j]
                        if j == nw - 1:
                            delw = wave[k, j] - wave[k, j - 1]

                        # integrate over D-flat fast vector
                        dfrqe_wav = dfrqe.field("WAVELENGTH")
                        dfrqe_rqe = dfrqe.field("RQE")
                        iw = np.where((dfrqe_wav >= wave[k, j] - delw / 2.) & (dfrqe_wav <= wave[k, j] + delw / 2.))
                        int_tab = auxfunc.idl_tabulate(dfrqe_wav[iw], dfrqe_rqe[iw])
                        first_dfrqe_wav, last_dfrqe_wav = dfrqe_wav[iw[0]][0], dfrqe_wav[iw[0]][-1]
                        dff = int_tab / (last_dfrqe_wav - first_dfrqe_wav)

                        if debug:
                            print("np.shape(dfrqe_wav) : ", np.shape(dfrqe_wav))
                            print("np.shape(dfrqe_rqe) : ", np.shape(dfrqe_rqe))
                            print("dfimdq[pind[0],[pind[1]] : ", dfimdq[pind[0], pind[1]])
                            print("np.shape(iw) =", np.shape(iw))
                            print("np.shape(dfrqe_wav) = ", np.shape(dfrqe_wav[iw]))
                            print("np.shape(dfrqe_rqe) = ", np.shape(dfrqe_rqe[iw]))
                            print("int_tab=", int_tab)
                            print("np.shape(dfim) = ", np.shape(dfim))
                            print("dff = ", dff)

                        # interpolate over D-flat cube
                        iloc = auxfunc.idl_valuelocate(dfwave, wave[k, j])[0]
                        if dfwave[iloc] > wave[k, j]:
                            iloc -= 1
                        ibr = [iloc]
                        if iloc != len(dfwave) - 1:
                            ibr.append(iloc + 1)
                        # get the values in the z-array at indeces ibr, and x=pind[1] and y=pind[0]
                        zz = dfim[:, pind[0], pind[1]][ibr]
                        # now determine the length of the array with only the finite numbers
                        zzwherenonan = np.where(np.isfinite(zz))
                        kk = np.size(zzwherenonan)
                        dfs = 1.0
                        if (wave[k, j] <= max(dfwave)) and (wave[k, j] >= min(dfwave)) and (kk == 2):
                            dfs = np.interp(wave[k, j], dfwave[ibr], zz[zzwherenonan])

                        # check DQ flags
                        if dfimdq[pind[0]][pind[1]] != 0:
                            dfs = 1.0

                        if debug:
                            print("wave[k, j] = ", wave[k, j])
                            print("iloc = ", iloc)
                            print("ibr = ", ibr)
                            print("np.interp(wave[k, j], dfwave[ibr], zz[zzwherenonan]) = ",
                                  np.interp(wave[k, j], dfwave[ibr], zz[zzwherenonan]))
                            print("dfs = ", dfs)

                        # integrate over S-flat fast vector
                        sfv_wav = sfv.field("WAVELENGTH")
                        sfv_dat = sfv.field("DATA")
                        iw = np.where((sfv_wav >= wave[k, j] - delw / 2.0) & (sfv_wav <= wave[k, j] + delw / 2.0))
                        sff = 1.0
                        if np.size(iw) > 2:
                            int_tab = auxfunc.idl_tabulate(sfv_wav[iw], sfv_dat[iw])
                            first_sfv_wav, last_sfv_wav = sfv_wav[iw[0]][0], sfv_wav[iw[0]][-1]
                            sff = int_tab / (last_sfv_wav - first_sfv_wav)
                        # get s-flat pixel-dependent correction
                        sfs = 1.0
                        if sfimdq[pind[0], pind[1]] == 0:
                            sfs = sfim[pind[0], pind[1]]

                        if debug:
                            print("np.shape(iw) =", np.shape(iw))
                            print("np.shape(sfv_wav) = ", np.shape(sfv_wav))
                            print("np.shape(sfv_dat) = ", np.shape(sfv_dat))
                            print("int_tab = ", int_tab)
                            print("sff = ", sff)
                            print("sfs = ", sfs)

                        # integrate over F-flat fast vector
                        # reference file blue cutoff is 1 micron, so need to force solution for shorter wavs
                        ffv_wav = ffv.field("WAVELENGTH")
                        ffv_dat = ffv.field("DATA")
                        fff = 1.0
                        if wave[k, j] - delw / 2.0 >= 1.0:
                            iw = np.where((ffv_wav >= wave[k, j] - delw / 2.0) & (ffv_wav <= wave[k, j] + delw / 2.0))
                            if np.size(iw) > 1:
                                int_tab = auxfunc.idl_tabulate(ffv_wav[iw], ffv_dat[iw])
                                first_ffv_wav, last_ffv_wav = ffv_wav[iw[0]][0], ffv_wav[iw[0]][-1]
                                fff = int_tab / (last_ffv_wav - first_ffv_wav)

                        flatcor[k, j] = dff * dfs * sff * sfs * fff

                        if debug:
                            print("np.shape(iw) =", np.shape(iw))
                            print("np.shape(ffv_wav) = ", np.shape(ffv_wav))
                            print("np.shape(ffv_dat) = ", np.shape(ffv_dat))
                            print("fff = ", fff)
                            print("flatcor[k, j] = ", flatcor[k, j])
                            print("dff, dfs, sff, sfs, fff:", dff, dfs, sff, sfs, fff)

                        try:
                            # Difference between pipeline and calculated values
                            delf[k, j] = pipeflat[k, j] - flatcor[k, j]

                            if debug:
                                print("delf[k, j] = ", delf[k, j])

                            # Remove all pixels with values=1 (outside slit boundaries) for statistics
                            if pipeflat[k, j] == 1:
                                delf[k, j] = 999.0
                            if np.isnan(wave[k, j]):
                                flatcor[k, j] = 1.0  # no correction if no wavelength

                            if debug:
                                print("flatcor[k, j] = ", flatcor[k, j])
                                print("delf[k, j] = ", delf[k, j])
                        except:
                            IndexError

            if debug:
                no_999 = delf[np.where(delf != 999.0)]
                print("np.shape(no_999) = ", np.shape(no_999))
                alldelf = delf.flatten()
                print("median of the whole array: ", np.median(alldelf))
                print("median, stdev in delf: ", np.median(no_999), np.std(no_999))
                neg_vals = no_999[np.where(no_999 < 0.0)]
                print("neg_vals = ", np.shape(neg_vals))
                print("np.shape(delf) = ", np.shape(delf))
                print("np.shape(delfg) = ", np.shape(delfg))

            nanind = np.isnan(delf)  # get all the nan indexes
            notnan = ~nanind  # get all the not-nan indexes
            delf = delf[notnan]  # get rid of NaNs
            if delf.size == 0:
                msg1 = " * Unable to calculate statistics because difference array has all values as NaN. Test will be set to FAILED."
                print(msg1)
                log_msgs.append(msg1)
                test_result = "FAILED"
                delfg_mean, delfg_median, delfg_std = np.nan, np.nan, np.nan
                stats = [delfg_mean, delfg_median, delfg_std]
            else:
                msg = "Calculating statistics... "
                print(msg)
                log_msgs.append(msg)
                delfg = delf[np.where((delf != 999.0) & (delf < 0.1) & (delf > -0.1))]  # ignore outliers
                if delfg.size == 0:
                    msg1 = " * Unable to calculate statistics because difference array has all outlier values. Test will be set to FAILED."
                    print(msg1)
                    log_msgs.append(msg1)
                    test_result = "FAILED"
                    delfg_mean, delfg_median, delfg_std = np.nan, np.nan, np.nan
                    stats = [delfg_mean, delfg_median, delfg_std]
                else:
                    stats_and_strings = auxfunc.print_stats(delfg, "Flat Difference", float(threshold_diff), abs=True)
                    stats, stats_print_strings = stats_and_strings
                    delfg_mean, delfg_median, delfg_std = stats
                    for msg in stats_print_strings:
                        log_msgs.append(msg)

                    # This is the key argument for the assert pytest function
                    median_diff = False
                    if abs(delfg_median) <= float(threshold_diff):
                        median_diff = True
                    if median_diff:
                        test_result = "PASSED"
                    else:
                        test_result = "FAILED"

            msg = " *** Result of the test: " + test_result + "\n"
            print(msg)
            log_msgs.append(msg)
            total_test_result.append(test_result)

            # make histogram
            if show_figs or save_figs:

                # set plot variables
                main_title = filt + "   " + grat + "   SLIT=" + slit_id + "\n"
                bins = None  # binning for the histograms, if None the function will select them automatically
                #             lolim_x, uplim_x, lolim_y, uplim_y
                plt_origin = None

                # Residuals img and histogram
                title = main_title + "Residuals"
                info_img = [title, "x (pixels)", "y (pixels)"]
                xlabel, ylabel = "flat$_{pipe}$ - flat$_{calc}$", "N"
                info_hist = [xlabel, ylabel, bins, stats]
                if delfg.size != 0 and delfg[1] is np.nan:
                    msg = "Unable to create plot of relative wavelength difference."
                    print(msg)
                    log_msgs.append(msg)
                else:
                    file_path = step_input_filename.replace(os.path.basename(step_input_filename), "")
                    file_basename = os.path.basename(step_input_filename.replace(".fits", ""))
                    t = (file_basename, "FS_flattest_" + slit_id + "_histogram.pdf")
                    plt_name = "_".join(t)
                    plt_name = os.path.join(file_path, plt_name)
                    difference_img = (pipeflat - flatcor)  # /flatcor
                    in_slit = np.logical_and(difference_img < 900.0,
                                             difference_img > -900.0)  # ignore points out of the slit,
                    difference_img[~in_slit] = np.nan  # Set values outside the slit to NaN
                    # nanind = np.isnan(difference_img)   # get all the nan indexes
                    # difference_img[nanind] = np.nan   # set all nan indexes to have a value of nan
                    vminmax = [-5 * delfg_std,
                               5 * delfg_std]  # set the range of values to be shown in the image, will affect color scale
                    auxfunc.plt_two_2Dimgandhist(difference_img, delfg, info_img, info_hist, plt_name=plt_name,
                                                 vminmax=vminmax,
                                                 plt_origin=plt_origin, show_figs=show_figs, save_figs=save_figs)

            elif not save_figs and not show_figs:
                msg = "Not making plots because both show_figs and save_figs were set to False."
                print(msg)
                log_msgs.append(msg)
            elif not save_figs:
                msg = "Not saving plots because save_figs was set to False."
                print(msg)
                log_msgs.append(msg)

            # create fits file to hold the calculated flat for each slit
            if writefile:
                msg = "Saving the fits files with the calculated flat for each slit..."
                print(msg)
                log_msgs.append(msg)

                # this is the file to hold the image of pipeline-calculated difference values
                outfile_ext = fits.ImageHDU(flatcor, name=slit_id)
                outfile.append(outfile_ext)

                # this is the file to hold the image of pipeline-calculated difference values
                complfile_ext = fits.ImageHDU(delf, name=slit_id)
                complfile.append(complfile_ext)

                # the file is not yet written, indicate that this slit was appended to list to be written
                msg = "Extension " + repr(
                    i) + " appended to list to be written into calculated and comparison fits files."
                print(msg)
                log_msgs.append(msg)

    if writefile:
        outfile_name = step_input_filename.replace("flat_field.fits", det + "_flat_calc.fits")
        complfile_name = step_input_filename.replace("flat_field.fits", det + "_flat_comp.fits")

        # create the fits list to hold the calculated flat values for each slit
        outfile.writeto(outfile_name, overwrite=True)

        # this is the file to hold the image of pipeline-calculated difference values
        complfile.writeto(complfile_name, overwrite=True)

        msg = "\nFits file with calculated flat values of each slit saved as: "
        print(msg)
        log_msgs.append(msg)
        print(outfile_name)
        log_msgs.append(outfile_name)

        msg = "Fits file with comparison (pipeline flat - calculated flat) saved as: "
        print(msg)
        log_msgs.append(msg)
        print(complfile_name)
        log_msgs.append(complfile_name)

    # If all tests passed then pytest will be marked as PASSED, else it will be FAILED
    FINAL_TEST_RESULT = False
    for t in total_test_result:
        if t == "FAILED":
            FINAL_TEST_RESULT = False
            break
        else:
            FINAL_TEST_RESULT = True

    if FINAL_TEST_RESULT:
        msg = "\n *** Final result for flat_field test will be reported as PASSED *** \n"
        print(msg)
        log_msgs.append(msg)
        result_msg = "All slits PASSED flat_field test."
    else:
        msg = "\n *** Final result for flat_field test will be reported as FAILED *** \n"
        print(msg)
        log_msgs.append(msg)
        result_msg = "One or more slits FAILED flat_field test."

    # end the timer
    flattest_end_time = time.time() - flattest_start_time
    if flattest_end_time > 60.0:
        flattest_end_time = flattest_end_time / 60.0  # in minutes
        flattest_tot_time = "* Script flattest_fs.py took ", repr(flattest_end_time) + " minutes to finish."
        if flattest_end_time > 60.0:
            flattest_end_time = flattest_end_time / 60.  # in hours
            flattest_tot_time = "* Script flattest_fs.py took ", repr(flattest_end_time) + " hours to finish."
    else:
        flattest_tot_time = "* Script flattest_fs.py took ", repr(flattest_end_time) + " seconds to finish."
    print(flattest_tot_time)
    log_msgs.append(flattest_tot_time)

    return FINAL_TEST_RESULT, result_msg, log_msgs


if __name__ == '__main__':
    # print pipeline version
    import jwst

    print("\n  ** using pipeline version: ", jwst.__version__, "** \n")

    # This is a simple test of the code
    pipeline_path = "/Users/pena/Documents/PyCharmProjects/nirspec/pipeline"

    # input parameters that the script expects
    # step_input_filename = pipeline_path+"/testing_data/FS_FULL_FRAME/G140M_opaque/gain_scale_NRS1_flat_field.fits"
    # step_input_filename = pipeline_path+"/testing_data/FS_ALLSLITS/G235H_F170LP/final_output_caldet1_NRS1_flat_field.fits"
    working_dir = '/Users/pena/Documents/PyCharmProjects/nirspec/pipeline/testing_data/BOTS/NID_41203'
    # working_dir = pipeline_path+"/testing_data/BOTS/NRSSRAD-G2H-PS-6007132838_1_491_SE_2016-01-07T17h03m08_491results"
    step_input_filename = working_dir + "/final_output_caldet1_NRS1_flat_field.fits"

    dflatref_path = "/grp/jwst/wit4/nirspec/CDP3/04_Flat_field/4.2_D_Flat/nirspec_dflat"
    sfile_path = "/grp/jwst/wit4/nirspec/CDP3/04_Flat_field/4.3_S_Flat/FS/nirspec_FS_sflat"
    fflat_path = "/grp/jwst/wit4/nirspec/CDP3/04_Flat_field/4.1_F_Flat/FS/nirspec_FS_fflat"
    # dflatref_path = "nirspec_dflat"
    # sfile_path = "nirspec_FS_sflat"
    # fflat_path = "nirspec_FS_fflat"

    # name of the output images
    writefile = True

    # set the names of the resulting plots
    plot_name = None  # "FS_flattest_histogram.pdf"

    # Run the principal function of the script
    median_diff = flattest(step_input_filename, dflatref_path=dflatref_path, sfile_path=sfile_path,
                           fflat_path=fflat_path, writefile=writefile, show_figs=False, save_figs=True,
                           plot_name=plot_name, threshold_diff=1.0e-7, debug=False)
