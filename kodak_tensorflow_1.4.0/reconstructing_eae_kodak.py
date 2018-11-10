"""A script to evaluate several trained entropy autoencoders, JPEG2000 and HEVC in terms of rate-distortion.

The trained entropy autoencoders, JPEG2000 and
HEVC are evaluated on the Kodak test set. Optionally,
the Kodak test set can be replaced by the BSDS
test set.

"""

import argparse
import matplotlib
try:
    import PyQt5
    matplotlib.use('Qt5Agg')
except ImportError:
    matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy
import os
import pickle
import tensorflow as tf

import eae.eae_utils as eaeuls
import hevc_utils.hevc_utils as hevculs
import jpeg2000.jpeg2000
import lossless.compression
import tools.tools as tls
from eae.graph.EntropyAutoencoder import EntropyAutoencoder
from eae.graph.IsolatedDecoder import IsolatedDecoder

def fix_gamma(reference_uint8, bin_width_init, multipliers, idx_training, gamma_scaling,
              are_bin_widths_learned, is_lossless, path_to_checking_r, list_rotation,
              positions_top_left):
    """Computes a series of pairs (rate, PSNR).
    
    A single entropy autoencoder is considered.
    At training time, the quantization bin widths
    were either fixed or learned.
    For each multiplier, the quantization bin widths
    at the end of the training are multiplied by the
    multiplier, yielding a set of test quantization bin
    widths. Then, for each set of test quantization bin
    widths, for each luminance image, the pair (rate, PSNR)
    associated to the compression of the luminance image
    via the single entropy autoencoder and the set of
    test quantization bin widths is computed.
    
    Parameters
    ----------
    reference_uint8 : numpy.ndarray
        3D array with data-type `numpy.uint8`.
        Luminance images. `reference_uint8[i, :, :]`
        is the ith luminance image.
    bin_width_init : float
        Value of the quantization bin widths
        at the beginning of the 1st training.
    multipliers : numpy.ndarray
        1D array with data-type `numpy.float32`.
        Multipliers.
    idx_training : int
        Training phase index of the single
        entropy autoencoder.
    gamma_scaling : float
        Scaling coefficient of the single
        entropy autoencoder.
    are_bin_widths_learned : bool
        Were the quantization bin widths learned
        at training time?
    is_lossless : bool
        Are the quantized latent variables coded
        losslessly?
    path_to_checking_r : str
        Path to the folder containing the luminance
        images before/after being compressed via the
        single entropy autoencoder.
    list_rotation : list
        Each integer in this list is the index
        of a rotated luminance image.
    positions_top_left : numpy.ndarray
        2D array with data-type `numpy.int32`.
        This array is dedicated to visualization.
        `positions_top_left[:, i]` contains the
        row and the column of the image pixel at
        the top-left of the ith crop of each
        luminance image after being compressed
        via the single entropy autoencoder.
    
    Returns
    -------
    tuple
        numpy.ndarray
            2D array with data-type `numpy.float64`.
            The element at the position [i, j] in this
            array is the rate associated to the compression
            of the jth luminance image via the single
            entropy autoencoder and the ith set of test
            quantization bin widths.
        numpy.ndarray
            2D array with data-type `numpy.float64`.
            The element at the position [i, j] in this
            array is the PSNR associated to the compression
            of the jth luminance image via the single
            entropy autoencoder and the ith set of test
            quantization bin widths.
    
    """
    nb_points = multipliers.size
    (nb_images, h_in, w_in) = reference_uint8.shape
    rate = numpy.zeros((nb_points, nb_images))
    psnr = numpy.zeros((nb_points, nb_images))
    if are_bin_widths_learned:
        suffix = 'learning_bw_{0}_{1}'.format(tls.float_to_str(bin_width_init), tls.float_to_str(gamma_scaling))
    else:
        suffix = '{0}_{1}'.format(tls.float_to_str(bin_width_init), tls.float_to_str(gamma_scaling))
    path_to_nb_itvs_per_side_load = 'eae/results/{0}/nb_itvs_per_side_{1}.pkl'.format(suffix, idx_training)
    path_to_restore = 'eae/results/{0}/model_{1}.ckpt'.format(suffix, idx_training)
    if is_lossless:
        path_to_vis = path_to_checking_r + 'reconstruction_fix_gamma/{}/lossless/'.format(suffix)
    else:
        path_to_vis = path_to_checking_r + 'reconstruction_fix_gamma/{}/approx/'.format(suffix)
    path_to_stats = 'lossless/results/{0}/training_index_{1}/'.format(suffix, idx_training)
    path_to_map_mean = os.path.join(path_to_stats, 'map_mean.npy')
    
    # A single entropy autoencoder is created.
    entropy_ae = EntropyAutoencoder(4,
                                    h_in,
                                    w_in,
                                    bin_width_init,
                                    gamma_scaling,
                                    path_to_nb_itvs_per_side_load,
                                    are_bin_widths_learned)
    with tf.Session() as sess:
        entropy_ae.initialization(sess, path_to_restore)
        y_float32 = eaeuls.encode_mini_batches(numpy.expand_dims(reference_uint8, axis=3),
                                               sess,
                                               entropy_ae,
                                               4)
        
        # `bin_widths` are the quantization bin widths
        # at the end of the training.
        bin_widths = entropy_ae.get_bin_widths()
    
    # The graph of the entropy autoencoder is destroyed.
    tf.reset_default_graph()
    
    # A single decoder is created.
    isolated_decoder = IsolatedDecoder(nb_images,
                                       h_in,
                                       w_in,
                                       are_bin_widths_learned)
    
    # The ith element of `map_mean` is the approximate
    # mean of the ith latent variable feature map. It
    # was computed on the extra set.
    map_mean = numpy.load(path_to_map_mean)
    tiled_map_mean = numpy.tile(map_mean, (nb_images, y_float32.shape[1], y_float32.shape[2], 1))
    
    # `idx_map_exception` was also computed on
    # the extra set.
    if is_lossless:
        with open(os.path.join(path_to_stats, 'idx_map_exception.pkl'), 'rb') as file:
            idx_map_exception = pickle.load(file)
    centered_y_float32 = y_float32 - tiled_map_mean
    with tf.Session() as sess:
        isolated_decoder.initialization(sess, path_to_restore)
        for i in range(nb_points):
            multiplier = multipliers[i].item()
            str_multiplier = tls.float_to_str(multiplier)
            bin_widths_test = multiplier*bin_widths
            centered_quantized_y_float32 = tls.quantize_per_map(centered_y_float32, bin_widths_test)
            off_centered_quantized_y_float32 = centered_quantized_y_float32 + tiled_map_mean
            reconstruction_float32 = sess.run(
                isolated_decoder.node_reconstruction,
                feed_dict={isolated_decoder.node_quantized_y:off_centered_quantized_y_float32}
            )
            
            # `reconstruction_uint8.dtype` is equal to `numpy.uint8`.
            # Its elements span the range [|16, 235|].
            reconstruction_uint8 = numpy.squeeze(tls.cast_bt601(reconstruction_float32), axis=3)
            
            # The binary probabilities were also computed
            # on the extra set.
            if is_lossless:
                path_to_binary_probabilities = os.path.join(path_to_stats, 'binary_probabilities_{}.npy'.format(str_multiplier))
            path_to_storage = path_to_vis + 'multiplier_{}/'.format(str_multiplier)
            for j in range(nb_images):
                if is_lossless:
                    nb_bits = lossless.compression.rescale_compress_lossless_maps(centered_quantized_y_float32[j, :, :, :],
                                                                                  bin_widths_test,
                                                                                  path_to_binary_probabilities,
                                                                                  idx_map_exception=idx_map_exception)
                    rate[i, j] = float(nb_bits)/(h_in*w_in)
                else:
                    rate[i, j] = tls.rate_3d(centered_quantized_y_float32[j, :, :, :],
                                             bin_widths_test,
                                             h_in,
                                             w_in)
                psnr[i, j] = tls.psnr_2d(reference_uint8[j, :, :],
                                         reconstruction_uint8[j, :, :])
                
                paths = [os.path.join(path_to_storage, 'reconstruction_{}.png'.format(j))]
                paths += [os.path.join(path_to_storage, 'reconstruction_{0}_crop_{1}.png'.format(j, index_crop)) for index_crop in range(positions_top_left.shape[1])]
                tls.visualize_rotated_luminance(reconstruction_uint8[j, :, :],
                                                j in list_rotation,
                                                positions_top_left,
                                                paths)
    
    # The graph of the decoder is destroyed.
    tf.reset_default_graph()
    return (rate, psnr)

def vary_gamma_fix_bin_widths(reference_uint8, bin_width_init, idxs_training, gammas_scaling,
                              path_to_checking_r, list_rotation, positions_top_left):
    """Computes a series of pairs (rate, PSNR).
    
    Several entropy autoencoders, each trained
    with a different scaling coefficient, are
    considered. At training time, the quantization
    bin widths were fixed.
    For each scaling coefficient, for each luminance
    image, the pair (rate, PSNR) associated to the
    compression of the luminance image via the entropy
    autoencoder trained with the scaling coefficient
    is computed.
    
    Parameters
    ----------
    reference_uint8 : numpy.ndarray
        3D array with data-type `numpy.uint8`.
        Luminance images. `reference_uint8[i, :, :]`
        is the ith luminance image.
    bin_width_init : float
        Value of the quantization bin widths
        at the beginning of the 1st training.
        In this function, the quantization bin
        widths are the same at training time
        and at test time.
    idxs_training : numpy.ndarray
        1D array with data-type `numpy.int32`.
        Its ith element is the training phase
        index of the entropy autoencoder trained
        with the ith scaling coefficient.
    gammas_scaling : numpy.ndarray
        1D array with data-type `numpy.float64`.
        Scaling coefficients.
    path_to_checking_r : str
        Path to the folder containing the
        luminance images before/after being
        compressed via entropy autoencoders.
    list_rotation : list
        Each integer in this list is the index
        of a rotated luminance image.
    positions_top_left : numpy.ndarray
        2D array with data-type `numpy.int32`.
        This array is dedicated to visualization.
        `positions_top_left[:, i]` contains the
        row and the column of the image pixel at
        the top-left of the ith crop of each
        luminance image after being compressed
        via entropy autoencoders.
    
    Returns
    -------
    tuple
        numpy.ndarray
            2D array with data-type `numpy.float64`.
            The element at the position [i, j] in this
            array is the rate associated to the compression
            of the jth luminance image via the entropy
            autoencoder trained with the ith scaling
            coefficient.
        numpy.ndarray
            2D array with data-type `numpy.float64`.
            The element at the position [i, j] in this
            array is the PSNR associated to the compression
            of the jth luminance image via the entropy
            autoencoder trained with the ith scaling
            coefficient.
    
    Raises
    ------
    AssertionError
        If `gammas_scaling.size` is not equal to
        `idxs_training.size`.
    
    """
    nb_points = gammas_scaling.size
    assert idxs_training.size == nb_points, '`gammas_scaling.size` is not equal to `idxs_training.size`.'
    (nb_images, h_in, w_in) = reference_uint8.shape
    rate = numpy.zeros((nb_points, nb_images))
    psnr = numpy.zeros((nb_points, nb_images))
    for i in range(nb_points):
        gamma_scaling = gammas_scaling[i].item()
        idx_training = idxs_training[i].item()
        suffix = '{0}_{1}'.format(tls.float_to_str(bin_width_init),
                                  tls.float_to_str(gamma_scaling))
        path_to_nb_itvs_per_side_load = 'eae/results/{0}/nb_itvs_per_side_{1}.pkl'.format(suffix, idx_training)
        path_to_restore = 'eae/results/{0}/model_{1}.ckpt'.format(suffix, idx_training)
        path_to_storage = path_to_checking_r + 'reconstruction_vary_gamma_fix_bin_widths/{}/'.format(suffix)
        
        # Every time `gamma_scaling` changes, a new
        # entropy autoencoder is created.
        entropy_ae = EntropyAutoencoder(4,
                                        h_in,
                                        w_in,
                                        bin_width_init,
                                        gamma_scaling,
                                        path_to_nb_itvs_per_side_load,
                                        False)
        with tf.Session() as sess:
            entropy_ae.initialization(sess, path_to_restore)
            y_float32 = eaeuls.encode_mini_batches(numpy.expand_dims(reference_uint8, axis=3),
                                                   sess,
                                                   entropy_ae,
                                                   4)
            
            # `bin_widths` are the quantization bin widths
            # at training time.
            bin_widths = entropy_ae.get_bin_widths()
        
        # The graph of the entropy autoencoder is destroyed.
        tf.reset_default_graph()
        
        # Every time `gamma_scaling` changes, a new
        # decoder is created.
        isolated_decoder = IsolatedDecoder(nb_images,
                                           h_in,
                                           w_in,
                                           False)
        quantized_y_float32 = tls.quantize_per_map(y_float32, bin_widths)
        with tf.Session() as sess:
            isolated_decoder.initialization(sess, path_to_restore)
            reconstruction_float32 = sess.run(
                isolated_decoder.node_reconstruction,
                feed_dict={isolated_decoder.node_quantized_y:quantized_y_float32}
            )
        
        # The graph of the decoder is destroyed.
        tf.reset_default_graph()
        
        # `reconstruction_uint8.dtype` is equal to `numpy.uint8`.
        # Its elements span the range [|16, 235|].
        reconstruction_uint8 = numpy.squeeze(tls.cast_bt601(reconstruction_float32), axis=3)
        for j in range(nb_images):
            rate[i, j] = tls.rate_3d(quantized_y_float32[j, :, :, :],
                                     bin_widths,
                                     h_in,
                                     w_in)
            psnr[i, j] = tls.psnr_2d(reference_uint8[j, :, :],
                                     reconstruction_uint8[j, :, :])
            
            paths = [os.path.join(path_to_storage, 'reconstruction_{}.png'.format(j))]
            paths += [os.path.join(path_to_storage, 'reconstruction_{0}_crop_{1}.png'.format(j, index_crop)) for index_crop in range(positions_top_left.shape[1])]
            tls.visualize_rotated_luminance(reconstruction_uint8[j, :, :],
                                            j in list_rotation,
                                            positions_top_left,
                                            paths)
    return (rate, psnr)

def write_reference(reference_uint8, path_to_checking_r, list_rotation, positions_top_left):
    """Writes the luminance images.
    
    Parameters
    ----------
    reference_uint8 : numpy.ndarray
        3D array with data-type `numpy.uint8`.
        Luminance images. `reference_uint8[i, :, :]`
        is the ith luminance image.
    path_to_checking_r : str
        Path to the folder containing the
        luminance images before/after being
        compressed via entropy autoencoders.
    list_rotation : list
        Each integer in this list is the index
        of a rotated luminance image.
    positions_top_left : numpy.ndarray
        2D array with data-type `numpy.int32`.
        This array is dedicated to visualization.
        `positions_top_left[:, i]` contains the
        row and the column of the image pixel at
        the top-left of the ith crop of each
        luminance image.
    
    """
    for i in range(reference_uint8.shape[0]):
        paths = [os.path.join(path_to_checking_r, 'reference/reference_{}.png'.format(i))]
        paths += [os.path.join(path_to_checking_r, 'reference/reference_{0}_crop_{1}.png'.format(i, index_crop)) for index_crop in range(positions_top_left.shape[1])]
        tls.visualize_rotated_luminance(reference_uint8[i, :, :],
                                        i in list_rotation,
                                        positions_top_left,
                                        paths)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Evaluates several trained entropy autoencoders, JPEG2000 and HEVC in terms of rate-distortion.')
    parser.add_argument('--code_lossless',
                        help='if given, the quantized latent variables are coded losslessly',
                        action='store_true',
                        default=False)
    parser.add_argument('--use_bsds',
                        help='if given, the BSDS test set is used. Otherwise, the Kodak test set is used',
                        action='store_true',
                        default=False)
    args = parser.parse_args()
    dict_vary_gamma_fix_bin_widths = {
        'bin_width_init': 1.,
        'idxs_training': numpy.array([10, 10, 10, 10, 10, 7, 6], dtype=numpy.int32),
        'gammas_scaling': numpy.array([10000., 12000., 16000., 24000., 40000., 72000., 96000.])
    }
    dict_fix_gamma_learn_bin_widths = {
        'bin_width_init': 0.5,
        'multipliers': numpy.array([1., 1.25, 1.5, 2., 3., 4., 6., 8., 10.], dtype=numpy.float32),
        'idx_training': 10,
        'gamma_scaling': 10000.
    }
    dict_fix_gamma_fix_bin_widths = {
        'bin_width_init': 1.,
        'multipliers': numpy.array([1., 1.25, 1.5, 2., 3., 4., 6., 8., 10.], dtype=numpy.float32),
        'idx_training': 10,
        'gamma_scaling': 10000.
    }
    
    # The height of the luminance images in the
    # BSDS test set is smaller than the height
    # of the luminance images in the Kodak test
    # set. The width of the luminance images in
    # the BSDS test set is smaller than the width
    # of the luminance images in the Kodak test set.
    if args.use_bsds:
        str_set = 'bsds'
        positions_top_left = numpy.array([[10, 110], [10, 110]], dtype=numpy.int32)
        title = 'Mean rate-distortion curves over the 100 BSDS luminance images'
    else:
        str_set = 'kodak'
        positions_top_left = numpy.array([[300, 200], [200, 300]], dtype=numpy.int32)
        title = 'Mean rate-distortion curves over the 24 Kodak luminance images'
    path_to_list_rotation = '{}/results/list_rotation.pkl'.format(str_set)
    path_to_checking_r = 'eae/visualization/test/checking_reconstructing/{}/'.format(str_set)
    
    # The block below is dedicated to JPEG2000.
    path_to_before_jpeg2000 = 'jpeg2000/visualization/{}/reference/'.format(str_set)
    path_to_after_jpeg2000 = 'jpeg2000/visualization/{}/reconstruction/'.format(str_set)
    qualities = [24, 26, 28, 30, 32, 34, 36, 38, 40]
    
    # The block below is dedicated to HEVC.
    path_to_before_hevc = 'hevc_utils/temp/luminance_before_hevc.yuv'
    path_to_after_hevc = 'hevc_utils/temp/luminance_after_hevc.yuv'
    path_to_cfg = 'hevc_utils/configuration/intra.cfg'
    path_to_bitstream = 'hevc_utils/temp/bitstream.bin'
    qps = numpy.array([22, 27, 32, 37, 42, 47], dtype=numpy.int32)
    path_to_hevc_vis = 'hevc_utils/visualization/{}/'.format(str_set)
    
    # `reference_uint8.dtype` is equal to `numpy.uint8`.
    reference_uint8 = numpy.load('{0}/results/{0}.npy'.format(str_set))
    with open(path_to_list_rotation, 'rb') as file:
        list_rotation = pickle.load(file)
    write_reference(reference_uint8,
                    path_to_checking_r,
                    list_rotation,
                    positions_top_left)
    
    (rate_vary_gamma_fix_bin_widths, psnr_vary_gamma_fix_bin_widths) = \
        vary_gamma_fix_bin_widths(reference_uint8,
                                  dict_vary_gamma_fix_bin_widths['bin_width_init'],
                                  dict_vary_gamma_fix_bin_widths['idxs_training'],
                                  dict_vary_gamma_fix_bin_widths['gammas_scaling'],
                                  path_to_checking_r,
                                  list_rotation,
                                  positions_top_left)
    numpy.save(os.path.join(path_to_checking_r, 'rate_vary_gamma_fix_bin_widths.npy'),
               rate_vary_gamma_fix_bin_widths)
    numpy.save(os.path.join(path_to_checking_r, 'psnr_vary_gamma_fix_bin_widths.npy'),
               psnr_vary_gamma_fix_bin_widths)
    
    # `str_code` enables to save the rate-distortion
    # performances of the approach below with/without
    # lossless coding in two separate files ".npy".
    if args.code_lossless:
        str_code = 'lossless'
    else:
        str_code = 'approx'
    (rate_fix_gamma_learn_bin_widths, psnr_fix_gamma_learn_bin_widths) = \
        fix_gamma(reference_uint8,
                  dict_fix_gamma_learn_bin_widths['bin_width_init'],
                  dict_fix_gamma_learn_bin_widths['multipliers'],
                  dict_fix_gamma_learn_bin_widths['idx_training'],
                  dict_fix_gamma_learn_bin_widths['gamma_scaling'],
                  True,
                  args.code_lossless,
                  path_to_checking_r,
                  list_rotation,
                  positions_top_left)
    numpy.save(os.path.join(path_to_checking_r, 'rate_fix_gamma_learn_bin_widths_{}.npy'.format(str_code)),
               rate_fix_gamma_learn_bin_widths)
    numpy.save(os.path.join(path_to_checking_r, 'psnr_fix_gamma_learn_bin_widths_{}.npy'.format(str_code)),
               psnr_fix_gamma_learn_bin_widths)
    
    (rate_fix_gamma_fix_bin_widths, psnr_fix_gamma_fix_bin_widths) = \
        fix_gamma(reference_uint8,
                  dict_fix_gamma_fix_bin_widths['bin_width_init'],
                  dict_fix_gamma_fix_bin_widths['multipliers'],
                  dict_fix_gamma_fix_bin_widths['idx_training'],
                  dict_fix_gamma_fix_bin_widths['gamma_scaling'],
                  False,
                  args.code_lossless,
                  path_to_checking_r,
                  list_rotation,
                  positions_top_left)
    numpy.save(os.path.join(path_to_checking_r, 'rate_fix_gamma_fix_bin_widths_{}.npy'.format(str_code)),
               rate_fix_gamma_fix_bin_widths)
    numpy.save(os.path.join(path_to_checking_r, 'psnr_fix_gamma_fix_bin_widths_{}.npy'.format(str_code)),
               psnr_fix_gamma_fix_bin_widths)
    
    (rate_jpeg2000, psnr_jpeg2000) = jpeg2000.jpeg2000.evaluate_jpeg2000(reference_uint8,
                                                                         path_to_before_jpeg2000,
                                                                         path_to_after_jpeg2000,
                                                                         qualities,
                                                                         list_rotation,
                                                                         positions_top_left)
    numpy.save(os.path.join(path_to_checking_r, 'rate_jpeg2000.npy'),
               rate_jpeg2000)
    numpy.save(os.path.join(path_to_checking_r, 'psnr_jpeg2000.npy'),
               psnr_jpeg2000)
    
    (rate_hevc, psnr_hevc) = hevculs.evaluate_hevc(reference_uint8,
                                                   path_to_before_hevc,
                                                   path_to_after_hevc,
                                                   path_to_cfg,
                                                   path_to_bitstream,
                                                   qps,
                                                   path_to_hevc_vis,
                                                   list_rotation,
                                                   positions_top_left)
    numpy.save(os.path.join(path_to_checking_r, 'rate_hevc.npy'),
               rate_hevc)
    numpy.save(os.path.join(path_to_checking_r, 'psnr_hevc.npy'),
               psnr_hevc)
    
    # The function `plt.plot` returns a list.
    handle = []
    handle.append(plt.plot(numpy.mean(rate_vary_gamma_fix_bin_widths, axis=1),
                           numpy.mean(psnr_vary_gamma_fix_bin_widths, axis=1),
                           color='orange',
                           marker='x',
                           markersize=9.)[0])
    handle.append(plt.plot(numpy.mean(rate_fix_gamma_learn_bin_widths, axis=1),
                           numpy.mean(psnr_fix_gamma_learn_bin_widths, axis=1),
                           color='green',
                           markerfacecolor='None',
                           marker='s',
                           markeredgecolor='green',
                           markersize=9.)[0])
    handle.append(plt.plot(numpy.mean(rate_fix_gamma_fix_bin_widths, axis=1),
                           numpy.mean(psnr_fix_gamma_fix_bin_widths, axis=1),
                           color='red',
                           markerfacecolor='None',
                           marker='o',
                           markeredgecolor='red',
                           markersize=9.)[0])
    handle.append(plt.plot(numpy.mean(rate_jpeg2000, axis=1),
                           numpy.mean(psnr_jpeg2000, axis=1),
                           color='black',
                           marker='>',
                           markersize=9.)[0])
    handle.append(plt.plot(numpy.mean(rate_hevc, axis=1),
                           numpy.mean(psnr_hevc, axis=1),
                           color='blue',
                           marker='<',
                           markersize=9.)[0])
    plt.title(title)
    plt.xlabel('mean rate (bbp)')
    plt.ylabel('mean PSNR (dB)')
    legend = [
        r'one learning per rate, $\{ \varphi_e, \varphi_d \}$ learned',
        r'unique learning, $\delta_i$ learned',
        r'unique learning, $\{ \varphi_e, \varphi_d \}$ learned',
        'JPEG2000',
        'H.265'
    ]
    plt.legend(handle,
               legend,
               loc='lower right',
               prop={'size': 14},
               frameon=False)
    plt.savefig(os.path.join(path_to_checking_r, 'rate_distortion.png'))
    plt.clf()


