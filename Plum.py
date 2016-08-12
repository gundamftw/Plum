import vapoursynth as vs
import math

fmtc_args                 = dict(fulls=True, fulld=True)
conv_args                 = dict(matrix=[1, 2, 1, 2, 4, 2, 1, 2, 1])
deconv_args               = dict(line=0, wn=0.48, fr=25, scale=0.28)
nnedi_args                = dict(field=1, dh=True, nns=4, qual=2, etype=1, nsize=0)

class helpers:
      def gauss(src, p):
          core            = vs.get_core()
          Resample        = core.fmtc.resample
          upsmp           = Resample(src, src.width * 2, src.height * 2, kernel="gauss", a1=100, **fmtc_args)
          clip            = Resample(upsmp, src.width, src.height, kernel="gauss", a1=p, **fmtc_args)
          return clip
      def cutoff(low, hi, p):
          core            = vs.get_core()
          MakeDiff        = core.std.MakeDiff
          MergeDiff       = core.std.MergeDiff
          hif             = MakeDiff(hi, helpers.gauss(hi, p))
          clip            = MergeDiff(helpers.gauss(low, p), hif)
          return clip
      def padding(src, left=0, right=0, top=0, bottom=0):
          core            = vs.get_core()
          Resample        = core.fmtc.resample
          w               = src.width
          h               = src.height
          clip            = Resample(src, w+left+right, h+top+bottom, -left, -top, w+left+right, h+top+bottom, kernel="point", **fmtc_args)
          return clip
      def deconvolution(src, radius):
          core            = vs.get_core()
          FQSharp         = core.vcfreq.Sharp
          sharp           = FQSharp(src, x=radius, y=radius, **deconv_args)
          clip            = helpers.cutoff(src, sharp, 1)
          return clip
      def convolution(src, strength):
          core            = vs.get_core()
          Resample        = core.fmtc.resample
          NNEDI           = core.nnedi3.nnedi3
          Transpose       = core.std.Transpose
          MakeDiff        = core.std.MakeDiff
          MergeDiff       = core.std.MergeDiff
          w               = src.width
          h               = src.height
          supersampled    = Transpose(NNEDI(Transpose(NNEDI(src, **nnedi_args)), **nnedi_args))
          blur            = Resample(supersampled, w*8, h*8, kernel="cubic", a1=strength, a2=0, **fmtc_args)
          sharp           = Resample(supersampled, w*8, h*8, kernel="cubic", a1=-strength, a2=0, **fmtc_args)
          dif             = Resample(MakeDiff(sharp, blur), w, h, sx=-0.5, sy=-0.5, kernel="cubic", a1=-1, a2=0, **fmtc_args)
          clip            = MergeDiff(src, dif)
          return clip
      def shrink(src):
          core            = vs.get_core()
          Convolution     = core.std.Convolution
          Expr            = core.std.Expr
          Crop            = core.std.CropRel
          MakeDiff        = core.std.MakeDiff
          Median          = core.std.Median
          MergeDiff       = core.std.MergeDiff
          blur            = Median(src)
          dif             = MakeDiff(blur, src)
          convD           = Convolution(dif, **conv_args)
          DD              = MakeDiff(dif, convD)
          convDD          = Convolution(DD, **conv_args)
          DDD             = Expr([DD, convDD], ["x y - x 0.5 - * 0 < 0.5 x y - abs x 0.5 - abs < x y - 0.5 + x ? ?"])
          dif             = MakeDiff(dif, DDD)
          convD           = Convolution(dif, **conv_args)
          dif             = Expr([dif, convD], ["y 0.5 - abs x 0.5 - abs > y 0.5 ?"])
          clip            = MergeDiff(src, dif)
          return clip
      def nlerror(src, a, h, ref):
          core            = vs.get_core()
          Crop            = core.std.CropRel
          KNLMeansCL      = core.knlm.KNLMeansCL
          pad             = helpers.padding(src, a, a, a, a)
          ref             = helpers.padding(ref, a, a, a, a)
          nlm             = KNLMeansCL(pad, d=0, a=a, s=0, h=h, rclip=ref)
          clip            = Crop(nlm, a, a, a, a)
          return clip

class internal:
      def basic(src, iterate, a, h, deconv_radius, conv_strength, mode):
          core            = vs.get_core()
          Expr            = core.std.Expr
          MakeDiff        = core.std.MakeDiff
          MergeDiff       = core.std.MergeDiff
          if mode == "deconvolution":
             sharp        = helpers.deconvolution(src, deconv_radius)
          else:
             sharp        = helpers.convolution(src, conv_strength)
          sharp           = helpers.nlerror(src, a[0], 0.001, sharp)
          local_error     = helpers.nlerror(src, a[1], h, src)
          local_limit     = MergeDiff(src, MakeDiff(src, local_error))
          limited         = Expr([sharp, local_limit, src], ["x z - abs y z - abs > y x ?"])
          clip            = helpers.shrink(limited)
          iterate        -= 1
          if iterate == 0:
             return clip
          else:
             return internal.basic(clip, iterate, a, h, deconv_radius, conv_strength, mode)

def Basic(src, iterate=3, a=[32, 1], h=64.0, deconv_radius=1, conv_strength=3.2, mode="deconvolution"):
    core                  = vs.get_core()
    RGB2OPP               = core.bm3d.RGB2OPP
    MakeDiff              = core.std.MakeDiff
    ShufflePlanes         = core.std.ShufflePlanes
    SetFieldBased         = core.std.SetFieldBased
    if not isinstance(src, vs.VideoNode):
       raise TypeError("Plum.Basic: src has to be a video clip!")
    elif src.format.sample_type != vs.FLOAT or src.format.bits_per_sample < 32:
       raise TypeError("Plum.Basic: the sample type of src has to be single precision!")
    if not isinstance(iterate, int):
       raise TypeError("Plum.Basic: iterate has to be an integer!")
    elif iterate < 1:
       raise RuntimeError("Plum.Basic: iterate has to be greater than 0!")
    if not isinstance(a, list):
       raise TypeError("Plum.Basic: a has to be an array!")
    elif len(a) != 2:
       raise RuntimeError("Plum.Basic: a has to contain 2 elements exactly!")
    elif not isinstance(a[0], int) or not isinstance(a[1], int):
       raise TypeError("Plum.Basic: elements in a must be integers!")
    if not isinstance(h, float) and not isinstance(h, int):
       raise TypeError("Plum.Basic: h has to be a real number!")
    elif h <= 0:
       raise RuntimeError("Plum.Basic: h has to be greater than 0!")
    if not isinstance(deconv_radius, int):
       raise TypeError("Plum.Basic: deconv_radius has to be an integer!")
    elif deconv_radius < 1:
       raise RuntimeError("Plum.Basic: deconv_radius has to be greater than 0!")
    if not isinstance(conv_strength, float) and not isinstance(conv_strength, int):
       raise TypeError("Plum.Basic: conv_strength has to be a real number!")
    elif conv_strength <= 0:
       raise RuntimeError("Plum.Basic: conv_strength has to be greater than 0!")
    if not isinstance(mode, str):
       raise TypeError("Plum.Basic: mode has to be a string!")
    elif mode.lower() != "deconvolution" and mode.lower() != "convolution":
       raise NotImplementedError("Plum.Basic: Undefined mode!")
    src                   = SetFieldBased(src, 0)
    colorspace            = src.format.color_family
    if colorspace == vs.RGB:
       src                = RGB2OPP(src, 1)
    if colorspace != vs.GRAY:
       src                = ShufflePlanes(src, 0, vs.GRAY)
    clip                  = internal.basic(src, iterate, a, h, deconv_radius, conv_strength, mode.lower())
    if mode.lower() == "deconvolution":
       clip               = MakeDiff(clip, src)
    return clip