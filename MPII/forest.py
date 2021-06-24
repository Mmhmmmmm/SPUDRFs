
import torch
import torch.nn as nn
from torch.autograd import Variable
from torch.nn.parameter import Parameter
from collections import OrderedDict
import numpy as np
import torch.nn.functional as F
import pickle

from utils.gaussian import multi_gaussian as gaussian_func
from utils.softmax import softmax

class Tree(nn.Module):
    def __init__(self,depth,n_in_feature):
        super(Tree, self).__init__()
        self.depth = depth
        self.n_leaf = 2 ** (depth - 1)

        # used features in this tree
        n_used_feature = self.n_leaf - 1
        onehot = np.eye(n_in_feature)

        using_idx = np.random.choice(np.arange(n_in_feature), n_used_feature, replace=False)
        self.feature_mask = onehot[using_idx].T
        self.feature_mask = Parameter(torch.from_numpy(self.feature_mask).type(torch.FloatTensor),requires_grad=False)


    def forward(self,x):
        """
        :param x(Variable): [batch_size,n_features]
        :return: route probability (Variable): [batch_size,n_leaf]
        """
        if x.is_cuda and not self.feature_mask.is_cuda:
            self.feature_mask = self.feature_mask.cuda()
        feats = torch.mm(x,self.feature_mask) # ->[batch_size,n_used_feature]
        decision = torch.sigmoid(feats) # ->[batch_size,n_leaf - 1]

        decision = torch.unsqueeze(decision,dim=2)
        decision_comp = 1-decision
        decision = torch.cat((decision,decision_comp),dim=2) # -> [batch_size,n_leaf,2]

        # compute route probability
        batch_size = x.size()[0]
        _mu = Variable(x.data.new(batch_size,1,1).fill_(1.))
        begin_idx = 0
        end_idx = 1
        for n_layer in range(0, self.depth - 1):
            _mu = _mu.view(batch_size,-1,1).repeat(1,1,2)
            _decision = decision[:, begin_idx:end_idx, :]  # -> [batch_size,2**n_layer,2]
            _mu = _mu*_decision # -> [batch_size,2**n_layer,2]
            begin_idx = end_idx
            end_idx = begin_idx + 2 ** (n_layer+1)

        mu = _mu.view(batch_size,self.n_leaf)
        #print(mu[:, :5])
        return mu

class Forest(nn.Module):
    '''
    :param \n
    n_tree, tree_depth, n_in_feature, num_classes, iterations_update_forest
    '''
    def __init__(self,n_tree,tree_depth,n_in_feature, num_classes, iterations_update_forest):
        super(Forest, self).__init__()
        self.trees = nn.ModuleList()
        self.n_tree  = n_tree
        self.num_classes = num_classes
        self.dist = Pi(n_tree, tree_depth, iter_num=iterations_update_forest)
        for _ in range(n_tree):
            tree = Tree(tree_depth,n_in_feature)
            self.trees.append(tree)

    def forward(self, x):
        probs = []
        for tree in self.trees:
            mu = tree(x)
            probs.append(mu.unsqueeze(2))
        
        pi = self.dist.get_mean() # 5, 32, task
        probs = torch.cat(probs,dim=2) # bs, 32, 5
        probs_ = probs.unsqueeze(3).repeat(1, 1, 1, pi.shape[-1]) # bs, 32, 5, task
        prob = probs_ * pi.transpose(0, 1).unsqueeze(0)     
        prob = torch.sum(prob, dim=1) 
        return prob, probs

class NeuralDecisionForest(nn.Module):
    def __init__(self, feature_layer, forest):
        super(NeuralDecisionForest, self).__init__()
        self.feature_layer = feature_layer
        self.forest = forest

    def forward(self, leye, reye, headpose):
        out, feat = self.feature_layer(leye, reye, headpose)
        out = out.view(out.size()[0],-1)
        prob, probs = self.forest(out)
        return prob, probs, feat

class Pi():
    def __init__(self, num_tree, tree_depth, iter_num=20, task_num=2):

        leaf_node_per_tree = 2 ** (tree_depth - 1)
        
        self.mean = np.random.rand(num_tree, leaf_node_per_tree, task_num, 1).astype(np.float32)
        self.sigma = np.random.rand(num_tree, leaf_node_per_tree, task_num, task_num).astype(np.float32)
        self.iter_num = iter_num
      
    def init_kmeans(self, mean, sigma):
        print('initialize mean by k-means')
        _, leaf_n, _, _ = self.mean.shape
        mean = np.expand_dims(mean, 2)
        for i in range(leaf_n):
            self.mean[:, i, :, :] = mean[i, :, :]
            self.sigma[:, i, :, :] = sigma[i, :, :]
            
    def get_mean(self, cuda=True):
        if cuda:
            return torch.tensor(self.mean).squeeze().cuda().float()
        else:
            return torch.tensor(self.mean).squeeze()

    def update(self, x, y):
        """
        x has the shape of [samples, num_tree, leaf_num],
        y hsa the shape of [samples, 1]
        gaussian_function will return a probability \\
        array with shape of [samples, num_tree, leaf_num].
        """
        print('update PI')
        num_tree, leaf_num, _, _  = self.mean.shape
        samples, task_num = y.shape
        for i in range(10):
            gaussian_value = gaussian_func(y, self.mean, self.sigma) # [samples, num_tree, leaf_num]
            all_leaf_prob_pi = x * (gaussian_value + 1e-9) # [samples, num_tree, leaf_num]
            all_leaf_sum_prob = np.sum(all_leaf_prob_pi, axis=2, keepdims=True)  # [samples, num_tree, 1]

            zeta = all_leaf_prob_pi / (all_leaf_sum_prob + 1e-9) # [samples, num_tree, leaf_num]

            y_temp = np.expand_dims(y, 2) # [samples, task_num, 1]
            y_temp = np.expand_dims(y_temp, 3) # [samples, task_num, 1, 1]
            y_temp = np.repeat(y_temp, num_tree, 2)
            y_temp = np.repeat(y_temp, leaf_num, 3) # [samples, task_num, num_tree, leaf_num]
            zeta = np.expand_dims(zeta, 1).repeat(task_num, 1) # [samples, task_num, num_tree, leaf_num]
            zeta_y = zeta * y_temp # [samples, task_num, num_tree, leaf_num]
            zeta_y = np.sum(zeta_y, 0) # [task_num, num_tree, leaf_num]
            zeta_sum  = np.sum(zeta, 0) # [task_num, num_tree, leaf_num]

            mean = zeta_y / (zeta_sum + 1e-9) # [task_num, num_tree, leaf_num]
            self.mean = mean.transpose(1, 2, 0).reshape(num_tree, leaf_num, task_num, 1)

            mean_new = y_temp - np.expand_dims(mean, 0).repeat(samples, 0) # [samples, task_num, num_tree, leaf_num]
            m1 = np.expand_dims(mean_new.transpose(0, 2, 3, 1), 4) # [samples, num_tree, leaf_num, task_num, 1]
            m2 = np.expand_dims(mean_new.transpose(0, 2, 3, 1), 3) # [samples, num_tree, leaf_num, 1, task_num]
            cov = np.matmul(m1, m2) # [samples, num_tree, leaf_num, task_num, task_num]
            zeta_for_sigma = np.expand_dims(zeta.transpose(0, 2, 3, 1), 4).repeat(task_num, 4) * cov # [samples, num_tree, leaf_num, task_num, task_num]
            zeta_for_sigma = np.sum(zeta_for_sigma, 0) # [num_tree, leaf_num, task_num, task_num]
            zeta_sum = np.expand_dims(zeta_sum.transpose(1,2,0), 3).repeat(task_num, 3) # [num_tree, leaf_num, task_num, task_num]
            sigma = zeta_for_sigma / (zeta_sum + 1e-9)
            self.sigma = sigma
        
    def save_model(self, path, pace, epoch):
        print('save PI at %s' % (path + str(pace) + 'pi_' + str(epoch)))
        with open(path + str(pace) + 'pi_' + str(epoch),'wb') as f:
            pickle.dump(self.mean, f)
            pickle.dump(self.sigma, f)

    def load_model(self, path, pace, epoch):
        print('load PI from %s' % (path + str(pace) + 'pi_' + str(epoch)))
        with open(path + str(pace) + 'pi_' + str(epoch) ,'rb') as f:
            self.mean = pickle.load(f)
            self.sigma = pickle.load(f)
        print('load PI successfully!')
