'''
Created on Jun 11, 2013

@author: justin
'''

from pycuda import gpuarray, driver as cuda, autoinit
import numpy as np
import cudaconv2
from pycuda import cumath
from util import *
from layer import *
import sys

class FastNet(object):
  def __init__(self, learningRate, imgShape, numOutput, initModel = None, autoAdd = True):
    self.learningRate = learningRate
    self.batchSize, self.numColor, self.imgSize, _ = imgShape
    self.imgShapes = [imgShape]
    self.inputShapes = [( self.numColor * (self.imgSize ** 2), self.batchSize)]
    self.numOutput = numOutput
    self.layers = []
    self.outputs = []
    self.grads = []

    self.numCase = self.cost = self.correct = 0.0

    if initModel:
      self.initLayer(initModel)
      return

    if autoAdd:
      self.autoAddLayer(numOutput)


  def makeLayerFromFASTNET(self, ld):
    if ld['type'] == 'conv':
      numFilter = ld['numFilter']
      filterSize = ld['filterSize']
      numColor = ld['numColor']
      padding = ld['paddinng']
      stride = ld['stride']
      initW = ld['initW']
      intB = ld['iniB']
      name = ld['name']
      epsW = ld['epsW']
      epsB = ld['epsB']
      imgSize = ls['imgSize']
      bias  = ld['biases']
      weight = ld['weight']
      name = ld['name']
      filter_shape = (numFilter, numColor, filterSize, filterSize)
      imge_shape = self.imgShapes[-1]
      return ConvLayer(name, filter_shape, img_shape, padding, stride, initW, initB, epsW, epsB,
          bias, weight)

    if ld['type'] == 'pool':
      stride = ld['stride']
      start = ld['start']
      poolSize = ld['poolSize']
      img_shape = self.imgShapes[-1]
      name = ld['name']
      return MaxPoolLayer(name, img_shape, poolSize, stride, start)

    if ld['type'] == 'neuron':
      if ld['neuron']['type'] == 'relu':
        img_shape = self.imgShapes[-1]
        name = ld['name']
        return NeuronLayer(name, img_shape, type = 'relue')

    if ld['type'] == 'fc':
      epsB = ld['epsB']
      epsW = ld['epsW']
      initB = ld['initB']
      initW = ld['initW']

      n_out = ld['outputs']
      bias = ld['biases']
      weight = ld['weights']
      name = ld['name']
      input_shape = self.inputShapes[-1]
      return FCLayer(name, input_shape, n_out, epsW, epsB, initW, initB, weight, bias)

    if ld['type'] == 'softmax':
      name = ld['name']
      input_shape = self.inputShapes[-1]
      return SoftmaxLayer(name, input_shape)

    if ld['type'] == 'rnorm':
      name = ld['name']
      pow = ld['pow']
      size = ld['size']
      scale = ld['scale']

      img_shape = self.imgShapes[-1]
      return ResponseNormLayer(name, img_shape, pow, size, scale)


  def makeLayerFromCUDACONVNET(self, ld):
    if ld['type'] == 'conv':
      numFilter = ld['filters']
      filterSize = ld['filterSize'][0]
      numColor = ld['channels'][0]
      padding = -ld['padding'][0]
      stride = ld['stride'][0]
      initW = ld['initW'][0]
      initB = ld['initB']
      name = ld['name']
      epsW = ld['epsW'][0]
      epsB = ld['epsB']

      imgSize = ld['imgSize']

      bias = ld['biases']
      weight = ld['weights'][0]

      filter_shape = (numFilter, numColor, filterSize, filterSize)
      img_shape = self.imgShapes[-1]
      return ConvLayer(name, filter_shape, img_shape, padding, stride, initW, initB, epsW, epsB, bias,
          weight)

    if ld['type'] == 'pool':
      stride = ld['stride']
      start = ld['start']
      poolSize = ld['sizeX']
      img_shape = self.imgShapes[-1]
      name = ld['name']
      return MaxPoolLayer(name, img_shape, poolSize, stride, start)

    if ld['type'] == 'neuron':
      if ld['neuron']['type'] == 'relu':
        img_shape = self.imgShapes[-1]
        name = ld['name']
        return NeuronLayer(name, img_shape, type = 'relu')

    if ld['type'] == 'fc':
      epsB = ld['epsB']
      epsW = ld['epsW'][0]
      initB = ld['initB']
      initW = ld['initW'][0]

      n_out = ld['outputs']
      bias = ld['biases']
      weight = ld['weights'][0].transpose()
      name = ld['name']
      input_shape = self.inputShapes[-1]
      return FCLayer(name, input_shape, n_out, epsW, epsB, initW, initB, weight, bias)

    if ld['type'] == 'softmax':
      name = ld['name']
      input_shape = self.inputShapes[-1]
      return SoftmaxLayer(name, input_shape)

    if ld['type'] == 'rnorm':
      name = ld['name']
      pow = ld['pow']
      size = ld['size']
      scale = ld['scale']

      img_shape = self.imgShapes[-1]
      return ResponseNormLayer(name, img_shape, pow, size, scale)


  def initLayer(self, m):
    layers = m['model_state']['layers']
    for l in layers:
      layer = self.makeLayerFromFASTNET(l)
      if layer:
        layer.scaleLearningRate(self.learningRate)
        self.append_layer(layer)

  def autoAddLayer(self, n_out):
    conv1 = ConvLayer('conv1', filter_shape = (64, 3, 5, 5), image_shape = self.imgShapes[-1],
        padding = 2, stride = 1, initW = 0.0001, epsW = 0.001, epsB = 0.002)
    conv1.scaleLearningRate(self.learningRate)
    self.append_layer(conv1)

    conv1_relu = NeuronLayer('conv1_neuron', self.imgShapes[-1])
    self.append_layer(conv1_relu)

    pool1 = MaxPoolLayer('pool1', self.imgShapes[-1], poolSize = 3, stride = 2, start = 0)
    self.append_layer(pool1)

    rnorm1 = ResponseNormLayer('rnorm1', self.imgShapes[-1], pow = 0.75, scale = 0.001, size = 9)
    self.append_layer(rnorm1)

    conv2 = ConvLayer('conv2',filter_shape = (64, 64, 5, 5) , image_shape = self.imgShapes[-1],
        padding = 2, stride = 1, initW=0.01, epsW = 0.001, epsB = 0.002)
    conv2.scaleLearningRate(self.learningRate)
    self.append_layer(conv2)

    conv2_relu = NeuronLayer('conv2_neuron', self.imgShapes[-1])
    self.append_layer(conv2_relu)

    rnorm2 = ResponseNormLayer('rnorm2', self.imgShapes[-1], pow = 0.75, scale = 0.001, size = 9)
    self.append_layer(rnorm2)

    pool2 = MaxPoolLayer('pool2', self.imgShapes[-1], poolSize= 3, start = 0, stride = 2)
    self.append_layer(pool2)

    fc1 = FCLayer('fc', self.inputShapes[-1], n_out)
    fc1.scaleLearningRate(self.learningRate)
    self.append_layer(fc1)

    softmax1 = SoftmaxLayer('softmax', self.inputShapes[-1])
    self.append_layer(softmax1)

  def add_parameterized_layers(self, n_filters = None, size_filters = None, fc_nout = [10]):
    if n_filters is None or n_filters == []:
      self.autoAddLayer(fc_nout[-1])
    else:
      for i in range(len(n_filters)):
        prev = n_filters[i-1] if i > 0 else self.imgShapes[-1][1]
        filter_shape = (n_filters[i], prev, size_filters[i], size_filters[i])
        conv = ConvLayer('conv' + str(i + 1), filter_shape, self.imgShapes[-1])
        self.append_layer(conv)
        conv.scaleLearningRate(self.learningRate)

        neuron = NeuronLayer('neuron'+str(i+1), self.imgShapes[-1])
        self.append_layer(neuron)

        pool = MaxPool('pool'+str(i + 1), self.imgShapes[-1])
        self.append_layer(pool)

        rnorm = ResponseLayer('rnorm'+str(i+1), self.imgShapes[-1])
        self.append_layer(rnorm)

      for i in range(len(fc_nout)):
        fc = FCLayer('fc'+str(i+1), self.inputShapes[-1], fc_nout[-1])
        self.append_layer(fc)

      self.append_layer(Softmax('softmax', self.inputShapes[-1]))

  def append_layer(self, layer):
    self.layers.append(layer)

    outputShape = layer.get_output_shape()
    row = outputShape[1] * outputShape[2] * outputShape[3]
    col = outputShape[0]
    self.inputShapes.append((row, col))
    self.imgShapes.append(outputShape)

    self.outputs.append(gpuarray.zeros((row, col), dtype = np.float32))
    self.grads.append(gpuarray.zeros(self.inputShapes[-2], dtype = np.float32))
    print 'append layer', layer.name, 'to network'
    print 'the output of the layer is', outputShape

  def del_layer(self):
    name = self.layers[-1]
    del self.layers[-1], self.inputShpaes[-1], self.imgShapes[-1], self.outputs[-1], self.grads[-1]
    print 'delete layer', name
    print 'the last layer would be', self.layers[-1].name

  def fprop(self, data, probs):
    input = data
    for i in range(len(self.layers)):
      l = self.layers[i]
      l.fprop(input, self.outputs[i])
      input = self.outputs[i]

    probs.shape = self.outputs[-1].shape
    gpu_copy_to(self.outputs[-1], probs)

  def bprop(self, data, label, prob):
    grad = label
    for i in range(1, len(self.layers) + 1):

      l = self.layers[-i]
      if l.diableBprop:
        return
      if i == len(self.layers):
        input = data
      else:
        input = self.outputs[-(i+1)]
      output = self.outputs[-i]
      outGrad = self.grads[-i]
      l.bprop(grad, input, output, outGrad)
      grad = outGrad

  def update(self):
    for l in self.layers:
      if l.diableBprop:
        return
      l.update()

  def get_cost(self, label, output):
    outputLayer = self.layers[-1]
    outputLayer.logreg_cost(label, output)
    return outputLayer.cost.get().sum(), outputLayer.batchCorrect

  def get_batch_information(self):
    cost = self.cost
    numCase = self.numCase
    correct = self.correct
    self.cost = self.numCase = self.correct = 0.0
    return cost/numCase , correct/ numCase, int(numCase)

  def get_correct(self):
    outputLayer = self.layers[-1]
    return outputLayer.get_correct()

  def train_batch(self, data, label, train = TRAIN):
    input = data
    self.numCase += input.shape[1]
    ########
    # The last minibatch of data_batch file may not be 1024
    ########
    if input.shape[1] != self.batchSize:
      self.batchSize = input.shape[1]
      for l in self.layers:
        l.change_batch_size(self.batchSize)
      self.inputShapes = None
      self.imgShapes = None
      self.outputs = []
      self.grads= []

      self.imgShapes = [(self.batchSize, self.numColor, self.imgSize, self.imgSize)]
      self.inputShapes = [( self.numColor * (self.imgSize ** 2), self.batchSize)]
      for layer in self.layers:
        outputShape = layer.get_output_shape()
        row = outputShape[1] * outputShape[2] * outputShape[3]
        col = outputShape[0]
        self.inputShapes.append((row, col))
        self.imgShapes.append(outputShape)

        self.outputs.append(gpuarray.zeros((row, col),dtype=np.float32))
        self.grads.append(gpuarray.zeros(self.inputShapes[-2], dtype=np.float32))

    outputShape = self.inputShapes[-1]
    output = gpuarray.zeros(outputShape, dtype=np.float32)

    if not isinstance(data, GPUArray):
      assert(isinstance(data, np.ndarray))
      data = gpuarray.to_gpu(data.astype(np.float32)) #.astype(np.float32))

    if not isinstance(label, GPUArray):
      assert(isinstance(label, np.ndarray))
      label = gpuarray.to_gpu(label.astype(np.float32))

    self.fprop(data, output)
    cost, correct = self.get_cost(label, output)
    self.cost += cost
    self.correct += correct
    if train == TRAIN:
      self.bprop(data, label, output)
      self.update()

  def get_dumped_layers(self):
    layers = []
    for l in self.layers:
      layers.append(l.dump() )

    return layers
  
  def disable_bprop(self):
    for l in self.layers:
      layers.disableBprop()

