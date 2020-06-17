import scipy.signal as signal
from scipy.optimize import curve_fit

import numpy as np

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec



import sys
import os

from matplotlib import rc
rc('text', usetex=True)

from helper_functions.utils_spiking import create_butter_bandpass, fit_func
import helper_functions.params_noisy_rate as pm

sys.path.append(os.path.dirname( __file__ ) + '/../../')
import bifurcation_analysis.figures_code.helper_functions.bifurcations as bif
import bifurcation_analysis.figures_code.helper_functions.aux_functions as aux

def plot_fig_12():
    data_spont = np.load('results/noisy_rate_model_long_sim_spont.npz', encoding='latin1', allow_pickle=True)
    dict_spont = dict(zip(("{}".format(k) for k in data_spont), (data_spont[k] for k in data_spont)))
    t_spont = dict_spont['t']
    b_spont = dict_spont['b']
    e_spont = dict_spont['e']
    b_pulses_spont = dict_spont['b_pulses']
    lowpass_b_spont = dict_spont['lowpass_b']
    peak_data_spont = dict_spont['peak_data']
    fit_data_spont = dict_spont['fit_data']

    data_evoke = np.load('results/noisy_rate_model_long_sim_evoke.npz', encoding='latin1', allow_pickle=True)
    dict_evoke = dict(zip(("{}".format(k) for k in data_evoke), (data_evoke[k] for k in data_evoke)))
    t_evoke = dict_evoke['t']
    b_evoke = dict_evoke['b']
    e_evoke = dict_evoke['e']
    b_pulses_evoke = dict_evoke['b_pulses']
    lowpass_b_evoke = dict_evoke['lowpass_b']
    peak_data_evoke = dict_evoke['peak_data']
    fit_data_evoke = dict_evoke['fit_data']
    b_pulses_onset = dict_evoke['b_pulses_onset']
    b_pulses_success = dict_evoke['b_pulses_success']

    fig_width = 17.6/2.54
    fig_height = 0.4*17.6/2.54

    fig = plt.figure(figsize=(fig_width,fig_height))
    gs = gridspec.GridSpec(5, 13, width_ratios=[1,1,1,1,1,1,0.2,1,1,1,1,1,1])
    gs_spont = gridspec.GridSpecFromSubplotSpec(5, 6, subplot_spec=gs[:, 0:6], height_ratios=[0.75,0.20,0.40,0.25,0.75])
    gs_evoke = gridspec.GridSpecFromSubplotSpec(5, 6, subplot_spec=gs[:, 7:13], height_ratios=[0.75,0.20,0.40,0.25,0.75])

    # t_plot_start = 195.4*1e3
    # t_plot_stop = 196.9*1e3
    t_plot_start = 51.*1e3
    t_plot_stop = 52.5*1e3

    plot_one_side(fig, gs_spont, 'spont', t_plot_start, t_plot_stop,\
                    t_spont, b_spont, e_spont, b_pulses_spont, lowpass_b_spont, peak_data_spont, fit_data_spont, None, None)
    plot_one_side(fig, gs_evoke, 'evoke', t_plot_start, t_plot_stop,\
                    t_evoke, b_evoke, e_evoke, b_pulses_evoke, lowpass_b_evoke, peak_data_evoke, fit_data_evoke, b_pulses_onset, b_pulses_success)

    plt.subplots_adjust(wspace=1., hspace=0.2)

    fig.savefig('results/fig_rate_model_noise.png',bbox_inches='tight', dpi=300)


def get_peak_data(t, b, b_pulses, sim_type):

    dt = t[1] - t[0]
    lowpass_b = filter_signal(b, dt, pm.b_findpeak_cutoff)
    peak_data, b_pulses_onset, b_pulses_success = find_peaks(t, lowpass_b, pm.b_findpeak_height, sim_type, b_pulses)

    if peak_data == False:
        fit_data = False
    else:
        _, _, peaks_duration_prev, peaks_duration_next, peaks_IEI_prev, peaks_IEI_next = peak_data
        fit_data = fit_exp(peaks_duration_prev, peaks_IEI_prev)


    print('Minimum IEI is %.1lf ms'%(np.min(peaks_IEI_prev)*1000))
    print('Time constant is %.1lf ms'%(1e3/fit_data[1][1]))

    return lowpass_b, peak_data, fit_data, b_pulses_onset, b_pulses_success

def find_peaks(t, lowpass_b, b_height, sim_type, b_pulses):
    # Find peaks:
    peaks, _ = signal.find_peaks(lowpass_b, height=b_height, prominence=b_height)

    # Find start and end points:
    start = np.zeros(peaks.size,dtype=int)
    end = np.zeros(peaks.size,dtype=int)
    duration = np.zeros(peaks.size)
    if peaks.size > 0:
        IEI = np.zeros(peaks.size-1, dtype=float)

        i = 0
        j = 0
        in_peak = False
        halfmax = lowpass_b[peaks[0]]/2
        while(i < t.size and j < peaks.size):

            if (in_peak == False) and (lowpass_b[i] > halfmax) and (i < peaks[j]):
                # print('passed start')
                start[j] = i
                in_peak = True

            if (in_peak == True) and (lowpass_b[i] < halfmax) and (i > peaks[j]):
                # print('passed end')
                end[j] = i
                in_peak = False

            if (j < peaks.size - 1) and (i > peaks[j]) and (peaks[j+1] - i < i - peaks[j]):
                j = j + 1
                halfmax = lowpass_b[peaks[j]]/2

            i = i + 1

        duration = t[end] - t[start]

        if (duration <= 0).any():
            print('ERROR: Failed finding peaks')
            return False

        # Calculate Inter-Event-Intervals:
        for i in range(peaks.size-1):
            IEI[i] = (t[start[i+1]] - t[end[i]])*1e-3 # convert to seconds

        duration_prev = 0
        duration_next = 0
        IEI_prev = 0
        IEI_next = 0
        b_pulses_onset = 0
        b_pulses_success = 0

        if (sim_type is 'spont'):
            duration_prev = duration[1:]
            duration_next = duration[:-1]
            IEI_prev = IEI
            IEI_next = IEI

        if (sim_type is 'evoke'):
            if b_pulses.any() > 0:

                # Get array with start of each pulse:
                for i in range(len(b_pulses) - 1):
                    if (b_pulses[i+1] > 0) and (b_pulses[i] == 0):
                        b_pulses_onset = np.append(b_pulses_onset,t[i])
                b_pulses_onset = b_pulses_onset[1:]
                # Check whether each pulse triggers a spike in the 20 ms following pulse onset:
                b_pulses_success = np.zeros_like(b_pulses_onset)
                evoked_peaks = np.array([-1])
                for i in range(len(b_pulses_onset)):
                    for j in range(peaks.size):
                        if (t[start[j]] - b_pulses_onset[i]) > 0 and (t[start[j]] - b_pulses_onset[i]) <= 20:
                            b_pulses_success[i] = 1
                            evoked_peaks = np.append(evoked_peaks,j)
                if len(evoked_peaks) > 1:
                    evoked_peaks = evoked_peaks[1:]
                    if (evoked_peaks[-1] == peaks.size - 1):
                        evoked_peaks = evoked_peaks[:-1]

                    # Get data only from evoked peaks:
                    start = start[evoked_peaks]
                    end = end[evoked_peaks]
                    duration_prev = duration[evoked_peaks]
                    duration_next = duration[evoked_peaks]
                    IEI_prev = IEI[evoked_peaks-1]
                    IEI_next = IEI[evoked_peaks]
                else:
                    evoked_peaks = 0
                    start = 0
                    end = 0
                    duration_prev = 0
                    duration_next = 0
                    IEI_prev = 0
                    IEI_next = 0
            else:
                peak_data = False

        peak_data = start, end, duration_prev, duration_next, IEI_prev, IEI_next
    else:
        peak_data = False
        b_pulses_onset = 0
        b_pulses_success = 0

    return peak_data, b_pulses_onset, b_pulses_success

def fit_exp(peaks_duration, peaks_IEI):
    try:
        fit_success = True
        fit_params, _ = curve_fit(fit_func, peaks_IEI, peaks_duration, p0=(2,2,68), bounds=(0,[100, 100, 100]))
    except:
        fit_success = False
        fit_params = None

    return fit_success, fit_params

def filter_signal(trace_spont, dt, highcut):
    # filter trace with Butterworth filter
    fs = 1e3/dt
    lowcut = -1.
    b, a = create_butter_bandpass(lowcut, highcut, fs, order=2, btype='low')
    filt_trace = signal.filtfilt(b, a, trace_spont)

    return filt_trace


def plot_one_side(fig, grid, sim_type, tstart, tstop, t, b, e, b_pulses, lowpass_b, peak_data, fit_data, b_pulses_onset, b_pulses_success):

    if len(peak_data) == 6:
        peaks_start, peaks_end, peaks_duration_prev, peaks_duration_next, peaks_IEI_prev, peaks_IEI_next = peak_data
    if fit_data != False:
        fit_success, fit_params = fit_data

    ax_t_B = fig.add_subplot(grid[0, 0:4])
    ax_t_e = fig.add_subplot(grid[1:3, 0:4])

    ax_e_B = fig.add_subplot(grid[0, 4:6])
    ax_IEI_hist = fig.add_subplot(grid[2, 4:6])

    ax_prev = fig.add_subplot(grid[4,0:3])
    ax_next = fig.add_subplot(grid[4,3:6])

    for ax in [ax_t_B, ax_t_e]:
        ax.set_xticks([])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.tick_params(axis='x', which='both', direction='in', bottom=False, top=False, labelbottom=False)
        ax.tick_params(axis='y', which='both', direction='in', bottom=False, top=False, labelbottom=False, labelsize=pm.fonts)
        ax.set_xlim([tstart,tstop])

    for ax in [ax_e_B, ax_IEI_hist, ax_prev, ax_next]:
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(axis='x', which='both', direction='in', bottom=True, top=False, labelbottom=True, labelsize=pm.fonts)
        ax.tick_params(axis='y', which='both', direction='in', bottom=False, top=False, labelbottom=False, labelsize=pm.fonts)

    ax_IEI_hist.spines['left'].set_visible(False)

    B_ticks = [0,45,90]

    if sim_type is 'spont':
        ax_t_B.set_title(r'\textbf{A1}',loc='left',x=-0.1,y=0.95,fontsize=pm.fonts)
        ax_t_B.set_title(r'Spontaneous',loc='center',x=0.75,y=1.20,fontsize=pm.fonts)
    else:
        ax_t_B.set_title(r'\textbf{A2}',loc='left',x=-0.1,y=0.95,fontsize=pm.fonts)
        ax_t_B.set_title(r'Evoked',loc='center',x=0.75,y=1.20,fontsize=pm.fonts)

    ax_t_B.plot(t, b, color='#3c3fef', lw=1.5)
    ax_t_B.plot(t, lowpass_b, color='black', lw=1.0)
    if (sim_type == 'evoke') and (b_pulses.any() > 0):
        ytop, ybottom = ax_t_B.get_ylim()
        ax_t_B.fill_between(t, ybottom, ytop, where = b_pulses > 0, facecolor='#d4b021')
        for i in range(len(b_pulses_onset)):
            if (b_pulses_onset[i] >= tstart) and (b_pulses_onset[i] <= tstop):
                if b_pulses_success[i] == 1:
                    ax_t_B.annotate('', xy=(b_pulses_onset[i], 0), xytext=(b_pulses_onset[i], -30),\
                        xycoords='data',arrowprops=dict(arrowstyle="->", lw=1.,color='black'))
                else:
                    ax_t_B.annotate('', xy=(b_pulses_onset[i], 0), xytext=(b_pulses_onset[i], -30),\
                        xycoords='data',arrowprops=dict(arrowstyle="->", lw=1.,color='lightgray'))
    ax_t_B.set_ylim([-0.1*B_ticks[-1],1.2*B_ticks[-1]])
    if sim_type is 'spont': ax_t_B.set_ylabel("B [1/s]",fontsize=pm.fonts)
    ax_t_B.set_yticks(B_ticks)
    ax_t_B.set_yticklabels(B_ticks,fontsize=pm.fonts)

    ax_t_e.plot(t, e, color='#e67e22', lw=1.5)
    ax_t_e.set_yticks([0.5,1.0])
    ax_t_e.set_yticklabels([0.5,1.0],fontsize=pm.fonts)
    ax_t_e.set_ylim([0.3,1.1])
    if sim_type is 'spont': ax_t_e.set_ylabel("e",fontsize=pm.fonts)

    bif_path = os.path.dirname( __file__ ) + '/../../bifurcation_analysis/bifurcation_diagrams/1param/'
    bs = bif.load_bifurcations(bif_path, 'e', 0, 1)

    if sim_type is 'spont':
        ax_e_B.set_title(r'\textbf{B1}',loc='left',x=-0.20,y=0.95,fontsize=pm.fonts)
    else:
        ax_e_B.set_title(r'\textbf{B2}',loc='left',x=-0.20,y=0.95,fontsize=pm.fonts)

    bif.plot_bifurcation(ax_e_B,aux,bs,'B',[0.25,1],1,'',[],[],B_ticks,'',pm.fonts,plot_color='gray',line_width=1.)
    ax_e_B.set_ylabel('',fontsize=pm.fonts)
    ax_e_B.plot(e[(t >= tstart) & (t <= tstop)], b[(t >= tstart) & (t <= tstop)], color='#3c3fef', lw=1.5)
    ax_e_B.set_ylim([-0.1*B_ticks[-1],1.2*B_ticks[-1]])
    ax_e_B.set_xlabel('e', fontsize=pm.fonts)

    if len(peak_data) == 6:

        if sim_type is 'spont':
            ax_IEI_hist.set_title(r'\textbf{C1}',loc='left',x=-0.20,y=0.85,fontsize=pm.fonts)
        else:
            ax_IEI_hist.set_title(r'\textbf{C2}',loc='left',x=-0.20,y=0.85,fontsize=pm.fonts)

        ax_IEI_hist.hist(peaks_IEI_prev,bins=30,color='gray')
        ax_IEI_hist.set_xlabel('IEI [s]',fontsize=pm.fonts)
        ax_IEI_hist.set_xlim([0,3])
        ax_IEI_hist.set_xticks([0,1,2])
        ax_IEI_hist.set_xticklabels([0,1,2],fontsize=pm.fonts)
        ax_IEI_hist.set_yticks([])
        ax_IEI_hist.set_yticklabels([])

        if fit_success == True:
            x_array = np.arange(np.min(peaks_IEI_prev),np.max(peaks_IEI_prev),0.01)

        if sim_type is 'spont':
            ax_prev.set_title(r'\textbf{D1}',loc='left',x=-0.15,y=0.95,fontsize=pm.fonts)
        else:
            ax_prev.set_title(r'\textbf{D2}',loc='left',x=-0.15,y=0.95,fontsize=pm.fonts)

        ax_prev.plot(peaks_IEI_prev, peaks_duration_prev, 'k.', ms=3)
        ax_prev.axvline(np.min(peaks_IEI_prev), linewidth=1, color='k', linestyle='--')
        if fit_success == True: ax_prev.plot(x_array,fit_func(x_array,*fit_params),color='red', lw=1.5)
        ax_prev.set_xlabel('previous IEI [s]',fontsize=pm.fonts)
        if sim_type is 'spont': ax_prev.set_ylabel('FWHM [ms]',fontsize=pm.fonts)
        ax_prev.set_ylim([30,110])
        ax_prev.set_yticks([50,100])
        ax_prev.set_yticklabels([50,100],fontsize=pm.fonts)
        ax_prev.set_xlim([0,3])
        ax_prev.set_xticks([0,1,2])
        ax_prev.set_xticklabels([0,1,2],fontsize=pm.fonts)

        ax_next.plot(peaks_IEI_next, peaks_duration_next, 'k.', ms=3)
        ax_next.set_xlabel('next IEI [s]',fontsize=pm.fonts)
        ax_next.set_yticklabels(labels=[],fontsize=pm.fonts)
        ax_next.set_ylim([30,110])
        ax_next.set_yticks([50,100])
        ax_next.set_xlim([0,3])
        ax_next.set_xticks([0,1,2])
        ax_next.set_xticklabels([0,1,2],fontsize=pm.fonts)