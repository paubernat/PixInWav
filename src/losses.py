import numpy as np
import torch
from pystct import isdct
import torch.nn.functional as F
from torch.autograd import Variable
from math import exp

def SNR(cover, container):
	cover_wav = isdct(cover.squeeze(0).squeeze(0).detach().numpy(), frame_step=62)
	container_wav = isdct(container.squeeze(0).squeeze(0).detach().numpy(), frame_step=62)
	
	signal = np.sum(np.abs(np.fft.fft(cover_wav)) ** 2) / len(np.fft.fft(cover_wav))
	noise = np.sum(np.abs(np.fft.fft(container_wav))**2) / len(np.fft.fft(container_wav))
	if noise <= 0.00001 or signal <= 0.00001: return 1
	return -1*(10 * np.log10(signal / noise))

def gaussian(window_size, sigma):
	gauss = torch.Tensor([exp(-(x - window_size//2)**2/float(2*sigma**2)) for x in range(window_size)])
	return gauss/gauss.sum()

def create_window(window_size, channel):
	_1D_window = gaussian(window_size, 1.5).unsqueeze(1)
	_2D_window = _1D_window.mm(_1D_window.t()).float().unsqueeze(0).unsqueeze(0)
	window = Variable(_2D_window.expand(channel, 1, window_size, window_size).contiguous())
	return window

def _ssim(img1, img2, window, window_size, channel, size_average = True):
	mu1 = F.conv2d(img1, window, padding = window_size//2, groups = channel)
	mu2 = F.conv2d(img2, window, padding = window_size//2, groups = channel)

	mu1_sq = mu1.pow(2)
	mu2_sq = mu2.pow(2)
	mu1_mu2 = mu1*mu2

	sigma1_sq = F.conv2d(img1*img1, window, padding = window_size//2, groups = channel) - mu1_sq
	sigma2_sq = F.conv2d(img2*img2, window, padding = window_size//2, groups = channel) - mu2_sq
	sigma12 = F.conv2d(img1*img2, window, padding = window_size//2, groups = channel) - mu1_mu2

	C1 = 0.01**2
	C2 = 0.03**2

	ssim_map = ((2*mu1_mu2 + C1)*(2*sigma12 + C2))/((mu1_sq + mu2_sq + C1)*(sigma1_sq + sigma2_sq + C2))
	
	if size_average:
		return ssim_map.mean()
	else:
		return ssim_map.mean(1).mean(1).mean(1)

class SSIM(torch.nn.Module):
	def __init__(self, window_size = 11, size_average = True):
		super(SSIM, self).__init__()
		self.window_size = window_size
		self.size_average = size_average
		self.channel = 1
		self.window = create_window(window_size, self.channel)

	def forward(self, img1, img2):
		(_, channel, _, _) = img1.size()

		if channel == self.channel and self.window.data.type() == img1.data.type():
			window = self.window
		else:
			window = create_window(self.window_size, channel)
			
			if img1.is_cuda:
				window = window.cuda(img1.get_device())
			window = window.type_as(img1)
			
			self.window = window
			self.channel = channel


		return _ssim(img1, img2, window, self.window_size, channel, self.size_average)

def ssim(img1, img2, window_size = 11, size_average = True):
	(_, channel, _, _) = img1.size()
	window = create_window(window_size, channel)
	
	if img1.is_cuda:
		window = window.cuda(img1.get_device())
	window = window.type_as(img1)
	
	return _ssim(img1, img2, window, window_size, channel, size_average)

def StegoLoss(secret, cover, container, container_2x, revealed, beta):

	loss_cover = F.mse_loss(cover, container)
	loss_secret = F.mse_loss(secret, revealed)
	loss_spectrum = F.mse_loss(container, container_2x)
	#gamma = (1/10) * SNR(cover.cpu(), container.cpu())
	#loss_cover = gamma * F.mse_loss(cover, container)
	#loss_secret = gamma * (1 - ssim(secret, revealed)) * F.mse_loss(secret, revealed)
	# loss = (1 - beta) * (loss_cover + loss_spectrum) + beta * loss_secret
	loss = (1 - beta) * (loss_cover) + beta * loss_secret
	return loss, loss_cover, loss_secret, loss_spectrum
