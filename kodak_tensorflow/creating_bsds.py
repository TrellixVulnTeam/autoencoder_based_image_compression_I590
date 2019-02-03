"""A script to create the BSDS test set."""

import argparse
import numpy

import datasets.bsds.bsds
import tools.tools as tls

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Creates the BSDS test set.')
    parser.add_argument('path_to_root',
                        help='path to the folder storing the original BSDS dataset')
    parser.add_argument('--path_to_tar',
                        help='path to the file "BSDS300-images.tgz", downloaded from <https://www2.eecs.berkeley.edu/Research/Projects/CS/vision/bsds/>',
                        default='',
                        metavar='')
    args = parser.parse_args()
    
    path_to_bsds = 'datasets/bsds/results/bsds.npy'
    
    datasets.bsds.bsds.create_bsds(args.path_to_root,
                                   path_to_bsds,
                                   'datasets/bsds/results/list_rotation.pkl',
                                   path_to_tar=args.path_to_tar)
    reference_uint8 = numpy.load(path_to_bsds)
    tls.save_image('datasets/bsds/visualization/luminance_7.png',
                   reference_uint8[7, :, :])
    tls.save_image('datasets/bsds/visualization/luminance_39.png',
                   reference_uint8[39, :, :])


