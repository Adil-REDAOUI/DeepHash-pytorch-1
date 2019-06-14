import numpy as np
import torch
import torch.nn as nn
from torch.autograd import Variable
from util import distance


def pairwise_loss(output, label, alpha=1.0, l_threshold=15.0, class_num=1.0):
    '''https://github.com/thuml/HashNet/issues/27#issuecomment-494265209'''
    bits = output.shape[1]
    similarity = Variable(torch.mm(label.data.float(), label.data.float().t()) > 0).float()
    dot_product = alpha * torch.mm(output, output.t()) / bits
    mask_dot = dot_product.data > l_threshold
    mask_exp = dot_product.data <= l_threshold
    mask_positive = similarity.data > 0
    mask_negative = similarity.data <= 0
    mask_dp = mask_dot & mask_positive
    mask_dn = mask_dot & mask_negative
    mask_ep = mask_exp & mask_positive
    mask_en = mask_exp & mask_negative

    dot_loss = dot_product * (1-similarity)
    exp_loss = torch.log(1+torch.exp(dot_product)) - similarity * dot_product
    loss = (torch.sum(torch.masked_select(exp_loss, Variable(mask_ep))) + torch.sum(torch.masked_select(dot_loss, Variable(mask_dp)))) * class_num + \
            torch.sum(torch.masked_select(exp_loss, Variable(mask_en))) + torch.sum(torch.masked_select(dot_loss, Variable(mask_dn)))

    return loss / (torch.sum(mask_positive.float()) * class_num + torch.sum(mask_negative.float()))


def pairwise_loss_debug(output, label, alpha=5.0):
    '''https://github.com/thuml/HashNet/issues/17#issuecomment-443137529'''
    bits = output.shape[0]
    similarity = Variable(torch.mm(label.data.float(), label.data.float().t()) > 0).float()
    dot_product = alpha * torch.mm(output, output.t()) / bits
    mask_positive = similarity.data > 0
    mask_negative = similarity.data <= 0
    #weight
    S1 = torch.sum(mask_positive.float())
    S0 = torch.sum(mask_negative.float())
    S = S0 + S1
    exp_loss = torch.log(1+torch.exp(dot_product)) - similarity * dot_product
    exp_loss[similarity.data > 0] = exp_loss[similarity.data > 0] * (S / S1)
    exp_loss[similarity.data <= 0] = exp_loss[similarity.data <= 0] * (S / S0)
    loss = torch.sum(exp_loss) / S
    return loss


def contrastive_loss(output, label, margin=16):
    '''contrastive loss
    - Deep Supervised Hashing for Fast Image Retrieval
    '''
    batch_size = output.shape[0]
    S =  Variable(torch.mm(label.float(), label.float().t()))
    dist = distance(output)
    loss_1 = S * dist + (1 - S) * torch.max(margin - dist, torch.zeros_like(dist))
    loss = torch.sum(loss_1) / (batch_size*(batch_size-1))
    return loss


def quantization_loss(output):
    loss = torch.mean((torch.abs(output) - 1) ** 2)
    return loss