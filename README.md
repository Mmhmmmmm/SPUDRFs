# Self-Paced Deep Regression Forests with Consideration on Underrepresented Samples

Deep discriminative models (e.g. deep regression forests, deep Gaussian process) have been extensively studied recently to solve problems such as facial age estimation and head pose estimation. Most existing methods pursue to achieve robust and unbiased solutions through either learning more discriminative features, or weighting samples. We argue what is more desirable is to gradually learn to discriminate like our human being, and hence we resort to self-paced learning (SPL). Then, a natural question arises: can self-paced regime guide deep discriminative models to obtain more robust and less unbiased solutions? To this end, this paper proposes a new deep discriminative model – self-paced deep regression forests considering sample uncertainty (SPUDRFs). It builds up a new self-paced learning paradigm: easy and underrepresented samples first. This paradigm could be extended to combine with a variety of deep discriminative models. Extensive experiments on two computer vision tasks, i.e., facial age estimation and head pose estimation, demonstrate the efficacy of SPUDRFs, where state-of-the-art performances are achieved. For detailed algorithm and experiment results please see paper published soon.

## Transplant:

Like [DRFs](https://github.com/shenwei1231/caffe-DeepRegressionForests), if you have a different Caffe or CUDA version than this repository and would like to try out the proposed SPUDRFs layers, you can transplant the following code to your repository.

(util) 

- include/caffe/util/sampling.hpp
- src/caffe/util/sampling.cpp
- include/caffe/util/neural_decision_util_functions.hpp
- src/caffe/util/neural_decision_util_functions.cu

(training) 

- include/caffe/layers/neural_decision_reg_forest_loss_layer.hpp 
- src/caffe/layers/neural_decision_reg_forest_loss_layer.cpp
- src/caffe/layers/neural_decision_reg_forest_loss_layer.cu

- include/caffe/layers/neural_decision_reg_forest_layer.hpp 
- src/caffe/layers/neural_decision_reg_forest_layer.cpp
- src/caffe/layers/neural_decision_reg_forest_layer.cu
