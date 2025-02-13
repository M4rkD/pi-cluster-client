
import cv2, sys, time, os
import numpy as np
from scipy import interpolate
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from kinectlib.calibration import affine_calibration as affc

from settings import dmin, dmax, min_distance, nmeasurements
from settings import num_points, corner_cutting_steps
from settings import color_scale, flip_display_axis
from settings import mock_kinect

# Try loading the kinect libraries
try:
    print("Loading kinect libraries...")
    from freenect import sync_get_depth, sync_get_video
    from freenect import DEPTH_MM

    # Try getting data to check if the device is connected
    if not sync_get_depth(format=DEPTH_MM):
        mock_kinect = True
        print("Kinect data could not be read - falling back to mock input")
    else:
        print("Kinect libraries loaded")
except:
    print("Freenect library could not be loaded - falling back to mock input")
    mock_kinect = True

class KinectAdapter:
    def __init__(self):
        self.color_scale = color_scale

    def _get_depth(self):
        "This function is overriden in the kinect mock adapter"
        (depth, _) = sync_get_depth(format=DEPTH_MM)

        # create a copy, as kinect library mutates a single object by default
        depth = np.copy(depth)

        return depth

    def get_depth(self):
        depth = self._get_depth()

        if flip_display_axis:
            depth = np.fliplr(depth)

        return depth

    def _get_video(self):
        "This function is overriden in the kinect mock adapter"
        (rgb, _) = sync_get_video()

        return rgb

    def get_video(self):
        rgb = self._get_video()

        rgb = np.copy(rgb)

        # scale colours by colour calibration
        rgb[:, :, 0] = rgb[:, :, 0] * self.color_scale[0]
        rgb[:, :, 1] = rgb[:, :, 1] * self.color_scale[1]
        rgb[:, :, 2] = rgb[:, :, 2] * self.color_scale[2]

        if flip_display_axis:
            rgb = np.fliplr(rgb)

        return invert_color_order(rgb)

    def set_color_scale(self, color_scale):
        self.color_scale = color_scale

    def get_color_scale(self):
        return self.color_scale



class MockKinectAdapter(KinectAdapter):
    def __init__(self):
        super().__init__()
        # Use recorded Kinect data to mock the device. Load the data
        # from kinect_data.npy and color_kinect_data.npy here.
        self.current_frame = 0

        self.mock_depth = np.load("test_data/kinect_data.npy")
        self.mock_color = np.load("test_data/color_kinect_data.npy")

        mock_kinect = True

    def _get_depth(self):
        self.current_frame = self.current_frame + 1
        current_frame = self.current_frame % len(self.mock_depth)
        depth = np.copy(self.mock_depth[current_frame])

        return depth


    def _get_video(self):
        self.current_frame = self.current_frame % len(self.mock_color)
        rgb = np.copy(self.mock_color[self.current_frame])

        return rgb


if mock_kinect:
    device = MockKinectAdapter()
else:
    device = KinectAdapter()

def invert_color_order(rgb):
    return cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)


def threshold(d):
    t = d * (d >= 1) + dmax * (d < 1)
    t = (t - dmin) * (t > dmin)
    t = t * (d < dmax) + (dmax - dmin) * (d >= dmax)
    t = (t.astype(np.float32) * 255 / (dmax - dmin))
    return t


def measure_depth(n=1):
    global device

    depth = device.get_depth()
    depth = threshold(depth)
    depth = depth.astype(np.float32) / n
    for m in range(1, n):
        d = device.get_depth()
        d = threshold(d)
        d = d.astype(np.float32) / n
        depth += d
    return depth


def remove_background(im, bg):
    diff = im - bg
    return im * (diff < -3) + 254 * (diff >= -3)


def depth_to_depthimage(depth):
    cmap = plt.get_cmap('brg')
    depth = (depth / np.max(depth))
    depthimage_rgba = cmap(depth) * 127
    depthimage = np.delete(depthimage_rgba, 3, 2)

    return depthimage.astype(np.uint8)


def normalised_depth_to_contour(depth):
    cutimage = np.dstack((depth, depth, depth)).astype(np.uint8)

    #Find contour
    gray = cv2.cvtColor(cutimage, cv2.COLOR_BGR2GRAY)
    _, thresholded = cv2.threshold(gray, min_distance, 255,
                                   cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(
        thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    contour = max(contours, key=cv2.contourArea)
    return np.array(contour).astype(int)


def cut_corners(outline, n):
    for i in range(n):
        outline = np.append(outline, [outline[0, ]], axis=0)
        R = outline[1:]
        L = outline[:outline.shape[0] - 1]
        outline = 0.5 * L + 0.5 * R
    return outline


def transform_contour(contour, scale, offset):
    outline = contour[:, 0, :]
    outline = cut_corners(outline, corner_cutting_steps)
    tck, u = interpolate.splprep(outline.transpose(), s=10)
    du = 1 / (num_points)
    unew = np.arange(0, 1.0, du)
    outline = interpolate.splev(unew, tck)
    outline = np.array(outline)

    transformed_outline = np.copy(outline)

    # apply affine transform from calibration to contour
    transformed_outline = affc.affine_transform_contour_dtc(
        transformed_outline)

    # apply offset and scale to contour
    transformed_outline[0, :] = transformed_outline[0, :] * scale[0]
    transformed_outline[1, :] = transformed_outline[1, :] * scale[1]

    transformed_outline[0, :] = transformed_outline[0, :] + offset[0]
    transformed_outline[1, :] = transformed_outline[1, :] + offset[1]

    outline = outline.transpose().reshape((-1, 1, 2))
    transformed_outline = transformed_outline.transpose().reshape((-1, 1, 2))

    return outline.astype(int), transformed_outline.astype(int)


def images_and_outline(background, scale, offset):
    ''' Capture depth and color input and find the contour.
        Transform the contour to match the color image.
        Return copy on color input, rgb image representing the depth and
        the transformed contour '''

    capture_depth = measure_depth( nmeasurements )
    rgb_frame = np.copy(device.get_video())

    clean_depth = remove_background(capture_depth, background)
    contour = normalised_depth_to_contour(clean_depth)
    outline, transformed_outline = transform_contour(
        contour, scale, offset)

    # set rgb image visible
    depthimage = depth_to_depthimage(capture_depth)

    # add contour to images
    cv2.drawContours(depthimage, [outline], -1, (0, 0, 255), 2)

    rgb_frame_with_outline = np.copy(rgb_frame)
    cv2.drawContours(rgb_frame_with_outline, [transformed_outline], -1,
                (0, 0, 255), 2)

    return rgb_frame, rgb_frame_with_outline, depthimage, transformed_outline

# Mock data utility functions for testing
def get_mock_video():
    return np.load("test_data/color_image.npy")


def get_mock_depth():
    return np.load("test_data/depth_image.npy")


def get_mock_background_depth():
    return np.load("test_data/depth_background_image.npy")

