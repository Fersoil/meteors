import os
import sys
import torch

# TODO: This is a workaround to import the module from the src directory - should be fixed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
import meteors as mt


# Temporary solution for wavelengths
wavelengths = [
    462.08,
    465.27,
    468.47,
    471.67,
    474.86,
    478.06,
    481.26,
    484.45,
    487.65,
    490.85,
    494.04,
    497.24,
    500.43,
    503.63,
    506.83,
    510.03,
    513.22,
    516.42,
    519.61,
    522.81,
    526.01,
    529.2,
    532.4,
    535.6,
    538.79,
    541.99,
    545.19,
    548.38,
    551.58,
    554.78,
    557.97,
    561.17,
    564.37,
    567.56,
    570.76,
    573.96,
    577.15,
    580.35,
    583.55,
    586.74,
    589.94,
    593.14,
    596.33,
    599.53,
    602.73,
    605.92,
    609.12,
    612.32,
    615.51,
    618.71,
    621.91,
    625.1,
    628.3,
    631.5,
    634.69,
    637.89,
    641.09,
    644.28,
    647.48,
    650.67,
    653.87,
    657.07,
    660.27,
    663.46,
    666.66,
    669.85,
    673.05,
    676.25,
    679.45,
    682.64,
    685.84,
    689.03,
    692.23,
    695.43,
    698.62,
    701.82,
    705.02,
    708.21,
    711.41,
    714.61,
    717.8,
    721.0,
    724.2,
    727.39,
    730.59,
    733.79,
    736.98,
    740.18,
    743.38,
    746.57,
    749.77,
    752.97,
    756.16,
    759.36,
    762.56,
    765.75,
    768.95,
    772.15,
    775.34,
    778.54,
    781.74,
    784.93,
    788.13,
    791.33,
    794.52,
    797.72,
    800.92,
    804.11,
    807.31,
    810.51,
    813.7,
    816.9,
    820.1,
    823.29,
    826.49,
    829.68,
    832.88,
    836.08,
    839.28,
    842.47,
    845.67,
    848.86,
    852.06,
    855.26,
    858.46,
    861.65,
    864.85,
    868.04,
    871.24,
    874.44,
    877.63,
    880.83,
    884.03,
    887.22,
    890.42,
    893.62,
    896.81,
    900.01,
    903.21,
    906.4,
    909.6,
    912.8,
    915.99,
    919.19,
    922.39,
    925.58,
    928.78,
    931.98,
    935.17,
    938.37,
]


def test_band_mask():
    shape = (150, 240, 240)
    sample = torch.ones(shape)

    image = mt.Image(
        image=sample,
        wavelengths=wavelengths,
        orientation=("C", "H", "W"),
        binary_mask="artificial",
    )

    band_names_list = ["R", "G", "B"]

    band_mask, band_names = mt.Lime.get_band_mask(image, band_names_list)

    assert (
        band_names == {"R": 1, "G": 2, "B": 3}
    ), "There should be only 4 values in the band mask corresponding to R, G, B, and background"
    assert (
        len(torch.unique(band_mask)) == 4
    ), "There should be only 4 values in the band mask corresponding to R, G, B, and background"
    assert torch.equal(
        torch.unique(band_mask), torch.tensor([0, 1, 2, 3])
    ), "There should be only 4 values in the band mask corresponding to R, G, B, and background"
    for c in range(shape[0]):
        assert (
            len(torch.unique(band_mask[c, :, :])) == 1
        ), "On each channel there should be only one unique number"
