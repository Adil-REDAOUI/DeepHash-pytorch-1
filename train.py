import sys
import argparse
import os
import os.path as osp

import numpy as np
import torch
import torch.nn as nn
import torch.utils.data as util_data
import torch.optim as optim
from torch.autograd import Variable
from tensorboardX import SummaryWriter

import network
import loss
import pre_process as prep
from data_list import ImageList
from util import Logger
from pprint import pprint
from datetime import datetime


optim_dict = {"SGD": optim.SGD, "Adam": optim.Adam}
scheduler_dict = {"step": optim.lr_scheduler.StepLR}


def train(config):
    ## set pre-process
    prep_dict = {}
    prep_config = config["prep"]
    prep_dict["train_set"] = prep.image_train( \
                                resize_size=prep_config["resize_size"], \
                                crop_size=prep_config["crop_size"])

    ## prepare data
    dsets = {}
    dset_loaders = {}
    data_config = config["data"]
    dsets["train_set"] = ImageList(open(data_config["train_set"]["list_path"]).readlines(), \
                                transform=prep_dict["train_set"])
    dset_loaders["train_set"] = util_data.DataLoader(dsets["train_set"], \
            batch_size=data_config["train_set"]["batch_size"], \
            shuffle=True, num_workers=4)

    ## set base network
    net_config = config["network"]
    base_network = net_config["type"](**net_config["params"])
    use_gpu = torch.cuda.is_available()
    if use_gpu:
        base_network = base_network.cuda()
    base_network.train(True)
                
    ## set optimizer and scheduler
    optimizer_config = config["optimizer"]
    lr = optimizer_config["optim_params"]["lr"]
    parameter_list = [{"params":base_network.feature_layers.parameters(), "lr":lr}, \
                      {"params":base_network.hash_layer.parameters(), "lr":lr*10}]
    optimizer = optim_dict[optimizer_config["type"]](parameter_list, \
                **optimizer_config["optim_params"])
    scheduler = scheduler_dict[optimizer_config["lr_type"]](optimizer, \
                ** optimizer_config["lr_param"])

    ## tensorboardX
    writer = SummaryWriter(logdir=osp.join(config["output_path"], "tflog"))
    # writer.add_graph(base_network, input_to_model=(torch.rand(1, 3, 224, 224),))
    
    ## train
    len_train = len(dset_loaders["train_set"]) - 1
    for i in range(config["num_iter"]):
        scheduler.step()
        optimizer.zero_grad()

        if i % len_train == 0:
            train_iter = iter(dset_loaders["train_set"])
        inputs, labels = train_iter.next()
        if use_gpu:
            inputs, labels = Variable(inputs).cuda(), Variable(labels).cuda()
        else:
            inputs, labels = Variable(inputs), Variable(labels)
           
        outputs = base_network(inputs)
        similarity_loss = loss.pairwise_loss(outputs, labels, **config["loss"])

        similarity_loss.backward()
        optimizer.step()

        writer.add_scalar('loss', similarity_loss, i)

        if i % 100 == 0:
            print("{} #train# Iter: {:05d}, loss: {:.3f}".format(
                datetime.now(), i, similarity_loss.item()))
            
    writer.close()
    torch.save(nn.Sequential(base_network), osp.join(config["output_path"], \
        "iter_{:05d}_model.pth.tar".format(i+1)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='HashNet')
    parser.add_argument('--gpus', type=str, default='0', help="device id to run")
    parser.add_argument('--dataset', type=str, default='nus_wide', help="dataset name")
    parser.add_argument('--hash_bit', type=int, default=48, help="number of hash code bits")
    parser.add_argument('--net', type=str, default='ResNet50', help="base network type")
    parser.add_argument('--prefix', type=str, default='hashnet', help="save path prefix")
    parser.add_argument('--lr', type=float, default=0.0003, help="learning rate")
    parser.add_argument('--class_num', type=float, default=1.0, help="positive negative pairs balance weight")
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpus

    # train config  
    config = {}
    config["num_iter"] = 10000
    config["snapshot_interval"] = 3000
    config["dataset"] = args.dataset
    config["hash_bit"] = args.hash_bit
    config["output_path"] = "../snapshot/"+args.dataset+"_"+ \
                            str(args.hash_bit)+"bit_"+args.net+"_"+args.prefix

    config["prep"] = {"test_10crop":True, "resize_size":256, "crop_size":224}
    config["loss"] = {"l_threshold":15.0, "sigmoid_param":10./args.hash_bit, "class_num":args.class_num}
    config["optimizer"] = {"type":"SGD", "optim_params":{"lr":args.lr, "momentum":0.9, \
                            "weight_decay":0.0005, "nesterov":True}, 
                           "lr_type":"step", "lr_param":{"step_size":2000, "gamma":0.5} }

    # network config
    config["network"] = {}
    if "ResNet" in args.net:
        config["network"]["type"] = network.ResNetFc
        config["network"]["params"] = {"name":args.net, "hash_bit":args.hash_bit}
    elif "VGG" in args.net:
        config["network"]["type"] = network.VGGFc
        config["network"]["params"] = {"name":args.net, "hash_bit":args.hash_bit}
    elif "AlexNet" in args.net:
        config["network"]["type"] = network.AlexNetFc
        config["network"]["params"] = {"hash_bit":args.hash_bit}

    # dataset config
    if config["dataset"] == "imagenet":
        config["data"] = {"train_set":{"list_path":"../data/imagenet/train.txt", "batch_size":36}}
    elif config["dataset"] == "nus_wide":
        config["data"] = {"train_set":{"list_path":"../data/nus_wide/train.txt", "batch_size":36}}
    elif config["dataset"] == "coco":
        config["data"] = {"train_set":{"list_path":"../data/coco/train.txt", "batch_size":36}}
    elif config["dataset"] == "cifar":
        config["data"] = {"train_set":{"list_path":"../data/cifar/train.txt", "batch_size":36}}
    
    if not osp.exists(config["output_path"]):
        os.mkdir(config["output_path"])
    sys.stdout = Logger(osp.join(config["output_path"], "train.log"))

    pprint(config)
    train(config)
