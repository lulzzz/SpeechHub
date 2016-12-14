# authors : Wim Boes & Robbe Van Rompaey
# date: 11-10-2016 

# imports
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import os
import sys
import time
import numpy as np

if 'LD_LIBRARY_PATH' not in os.environ:
        os.environ['LD_LIBRARY_PATH'] = '/home/wim/cuda-8.0/lib64'
        try:
            	os.system('python ' + ' '.join(sys.argv))
                sys.exit(0)
        except Exception, exc:
                print('Failed re_exec:', exc)
                sys.exit(1)

import tensorflow as tf
import reader_cbow_sentence

##### paths

python_path = os.path.abspath(os.getcwd())
general_path = os.path.split(python_path)[0]
input_path = os.path.join(general_path,'input')
output_path = os.path.join(general_path,'output')

##### flags

flags = tf.flags
logging = tf.logging

### regular

flags.DEFINE_float("init_scale", 0.05, "init_scale")
flags.DEFINE_float("learning_rate", 1, "learning_rate")
flags.DEFINE_float("max_grad_norm", 5, "max_grad_norm")
flags.DEFINE_integer("num_layers", 1, "num_layers")
flags.DEFINE_integer("num_history", 100, "num_history")
flags.DEFINE_integer("hidden_size", 512, "hidden_size")
flags.DEFINE_integer("max_epoch", 6, "max_epoch")
flags.DEFINE_integer("max_max_epoch", 2, "max_max_epoch")
flags.DEFINE_float("keep_prob", 0.5, "keep_prob")
flags.DEFINE_float("lr_decay", 0.8, "lr_decay")
flags.DEFINE_integer("embedded_size_reg", 256, "embedded_size_reg")
flags.DEFINE_integer("embedded_size_cbow", 256, "embedded_size_cbow")

### general

flags.DEFINE_integer("batch_size", 40, "batch_size")
flags.DEFINE_integer("num_run", 0, "num_run")
flags.DEFINE_string("test_name","cbow_test","test_name")
flags.DEFINE_string("data_path",input_path,"data_path")
flags.DEFINE_string("save_path",output_path,"save_path")
flags.DEFINE_string("use_fp16",False,"train blabla")
flags.DEFINE_string("loss_function","full_softmax","loss_function")
flags.DEFINE_string("optimizer","Adagrad","optimizer")
flags.DEFINE_string("combination","mean","combination")
flags.DEFINE_string("position","lstm","position")


FLAGS = flags.FLAGS

##### classes and functions 

def data_type():
    return tf.float16 if FLAGS.use_fp16 else tf.float32


class ds_input(object):
    def __init__(self, config, max_length, word_to_id, data, name=None):
        self.batch_size = batch_size = config.batch_size
        self.num_history = num_history = config.num_history
        self.max_length = max_length
        self.epoch_size = (len(data) // batch_size)
        self.input_data, self.targets, _, self.history, self.average_sentence_length = reader_cbow_sentence.ds_producer(data, batch_size, max_length, num_history, word_to_id, name=name)

class cbow_model(object):

    def __init__(self, is_training, config, input_):
        self._input = input_

        batch_size = input_.batch_size
        hidden_size = config.hidden_size
        num_history = input_.num_history
        unk_id = config.unk_id
        vocab_size = config.vocab_size

        history_throw_away = 100
        
        seq_len = self.length_of_seq(input_.input_data, vocab_size)
        
        with tf.device("/cpu:0"):
            embedding_reg = tf.get_variable("embedding_reg", [vocab_size+1, config.embedded_size_reg], dtype=data_type())
            embedding_cbow = tf.get_variable("embedding_cbow", [vocab_size+1, config.embedded_size_cbow], dtype=data_type())
            inputs_reg = tf.nn.embedding_lookup(embedding_reg, input_.input_data)
            inputs_cbow = tf.nn.embedding_lookup(embedding_cbow, input_.history)

        if is_training and config.keep_prob < 1:
            inputs_reg = tf.nn.dropout(inputs_reg, config.keep_prob)
            inputs_cbow = tf.nn.dropout(inputs_cbow, config.keep_prob)

        with tf.variable_scope('cbow') as cbow:           
            outputs_cbow = []
            for i in range(input_.max_length):
                slice1 = tf.slice(input_.history,[0,i],[batch_size,num_history])
                slice2 = tf.slice(inputs_cbow,[0,i,0],[batch_size,num_history,config.embedded_size_cbow])
                
                if FLAGS.combination == "mean":
                    mask = tf.cast(tf.logical_and(tf.greater(slice1,[history_throw_away]), tf.not_equal(slice1,[vocab_size])), dtype = tf.float32)
                    mask1 = tf.pack([mask]*config.embedded_size_cbow,axis = 2)
                    out = mask1*slice2
                    comb_ = tf.reduce_sum(out,1)/(tf.reduce_sum(mask1,1) + 1e-32)
    
                if FLAGS.combination == "exp":
                    exp_weights = tf.reverse(tf.constant([[config.embedded_size_cbow*[np.exp(-5*k/num_history)] for k in range(num_history)] for j in range(batch_size)]),[False,True,False])
                    mask = tf.cast(tf.logical_and(tf.greater(slice1,[history_throw_away]), tf.not_equal(slice1,[vocab_size])), dtype = tf.float32)
                    mask1 = tf.pack([mask]*config.embedded_size_cbow,axis = 2)
                    out = mask1*slice2*exp_weights
                    comb_ = tf.reduce_sum(out,1)/(tf.reduce_sum(mask1*exp_weights,1) + 1e-32)
    
                outputs_cbow.append(comb_)
                output_cbow_soft = tf.reshape(tf.concat(1, outputs_cbow), [-1, config.embedded_size_cbow])
                output_cbow_lstm = tf.reshape(tf.concat(1, outputs_cbow), [batch_size,tf.squeeze(input_.max_length), config.embedded_size_cbow])
                # voor 'BeforeLSTMCbowReg'
            
        with tf.variable_scope('lstm_soft') as lstm_soft:
            
            lstm_cell_soft = tf.nn.rnn_cell.BasicLSTMCell(hidden_size, forget_bias=0.0, state_is_tuple=True)
            if is_training and config.keep_prob < 1:
                lstm_cell_soft = tf.nn.rnn_cell.DropoutWrapper(lstm_cell_soft, output_keep_prob=config.keep_prob)
            cell_soft = tf.nn.rnn_cell.MultiRNNCell([lstm_cell_soft] * config.num_layers, state_is_tuple=True)

            self._initial_state_soft = cell_soft.zero_state(batch_size, data_type())
   
            outputs_soft, state_soft = tf.nn.dynamic_rnn(cell_soft, inputs_reg, initial_state=self._initial_state_soft, dtype=tf.float32, sequence_length=seq_len)
            output_LSTM_soft = tf.reshape(tf.concat(1, outputs_soft), [-1, hidden_size])
            output_soft = tf.concat(1,[output_LSTM_soft,output_cbow_soft])

        with tf.variable_scope('lstm_lstm') as lstm_lstm:

            lstm_cell_lstm = tf.nn.rnn_cell.BasicLSTMCell(hidden_size, forget_bias=0.0, state_is_tuple=True)
            if is_training and config.keep_prob < 1:
                lstm_cell_lstm = tf.nn.rnn_cell.DropoutWrapper(lstm_cell_lstm, output_keep_prob=config.keep_prob)
            cell_lstm = tf.nn.rnn_cell.MultiRNNCell([lstm_cell_lstm] * config.num_layers, state_is_tuple=True)

            self._initial_state_lstm = cell_lstm.zero_state(batch_size, data_type())
            
            inputs_lstm = tf.concat(2,[inputs_reg, output_cbow_lstm])
            outputs_lstm, state_lstm = tf.nn.dynamic_rnn(cell_lstm, inputs_lstm, initial_state=self._initial_state_lstm, dtype=tf.float32)
            output_LSTM_lstm = tf.reshape(tf.concat(1, outputs_lstm), [-1, hidden_size])
            output_lstm = output_LSTM_lstm

        softmax_w_soft = tf.get_variable("softmax_w_soft", [hidden_size+config.embedded_size_cbow, vocab_size], dtype=data_type())
        softmax_b_soft = tf.get_variable("softmax_b_soft", [vocab_size], dtype=data_type())            
            
        softmax_w_lstm = tf.get_variable("softmax_w_lstm", [hidden_size, vocab_size], dtype=data_type())
        softmax_b_lstm = tf.get_variable("softmax_b_lstm", [vocab_size], dtype=data_type())            
            
        loss_soft = get_loss_function(output_soft, softmax_w_soft, softmax_b_soft, input_.targets, batch_size, is_training, unk_id, vocab_size)
        loss_lstm = get_loss_function(output_lstm, softmax_w_lstm, softmax_b_lstm, input_.targets, batch_size, is_training, unk_id, vocab_size)

        self._cost_soft = cost_soft = loss_soft
        self._cost_lstm = cost_lstm = loss_lstm
        
        if not is_training:
            return      

        self._lr = tf.Variable(0.0, trainable=False)
        tvars_soft = [embedding_reg, embedding_cbow, softmax_w_soft, softmax_b_soft] + [v for v in tf.trainable_variables() if v.name.startswith(lstm_soft.name)] + [v for v in tf.trainable_variables() if v.name.startswith(cbow.name)]
        grads_soft, _ = tf.clip_by_global_norm(tf.gradients(cost_soft, tvars_soft),config.max_grad_norm)   
        tvars_lstm = [embedding_reg, embedding_cbow, softmax_w_lstm, softmax_b_lstm] + [v for v in tf.trainable_variables() if v.name.startswith(lstm_lstm.name)] + [v for v in tf.trainable_variables() if v.name.startswith(cbow.name)]
        grads_lstm, _ = tf.clip_by_global_norm(tf.gradients(cost_lstm, tvars_lstm),config.max_grad_norm)   
        optimizer = get_optimizer(self._lr)
        self._train_op_soft = optimizer.apply_gradients(zip(grads_soft, tvars_soft),global_step=tf.contrib.framework.get_or_create_global_step())
        self._train_op_lstm = optimizer.apply_gradients(zip(grads_lstm, tvars_lstm),global_step=tf.contrib.framework.get_or_create_global_step())

        self._new_lr = tf.placeholder(tf.float32, shape=[], name="new_learning_rate")
        self._lr_update = tf.assign(self._lr, self._new_lr)
#            
#        if FLAGS.position == 'BeforeSoftmaxCbow':
#            output_cbow = tf.reshape(tf.concat(1, outputs_cbow), [-1, embedded_size])
#            
#            outputs, state = tf.nn.dynamic_rnn(cell, inputs_reg, initial_state=self._initial_state, dtype=tf.float32, sequence_length=seq_len)
#            output_LSTM = tf.reshape(tf.concat(1, outputs), [-1, hidden_size])
#            
#            softmax_w = tf.get_variable("softmax_w", [hidden_size+embedded_size, vocab_size], dtype=data_type())
#            softmax_b = tf.get_variable("softmax_b", [vocab_size], dtype=data_type())
#            output = tf.concat(1,[output_LSTM,output_cbow])
#        
#        if FLAGS.position == 'BeforeLSTMCbowReg':
#            output_cbow = tf.reshape(tf.concat(1, outputs_cbow), [batch_size,tf.squeeze(num_steps), embedded_size])
#            
#            inputs = tf.concat(2,[inputs_reg, output_cbow])
#            
#            outputs, state = tf.nn.dynamic_rnn(cell, inputs, initial_state=self._initial_state, dtype=tf.float32)
#            output_LSTM = tf.reshape(tf.concat(1, outputs), [-1, hidden_size])
#            
#            softmax_w = tf.get_variable("softmax_w", [hidden_size, vocab_size], dtype=data_type())
#            softmax_b = tf.get_variable("softmax_b", [vocab_size], dtype=data_type())
#            output = output_LSTM

            
#        loss = get_loss_function(output, softmax_w, softmax_b, input_.targets, batch_size, is_training, unk_id)
        
    def assign_lr(self, session, lr_value):
        session.run(self._lr_update, feed_dict={self._new_lr: lr_value})
    
    def length_of_seq(self,sequence, vocab_size):
        used = tf.sign(tf.abs(sequence-vocab_size))
        length = tf.reduce_sum(used, reduction_indices=1)
        length = tf.cast(length, tf.int32)
        return length

    @property
    def input(self):
        return self._input

    @property
    def initial_state_soft(self):
        return self._initial_state_soft
        
    @property
    def initial_state_lstm(self):
        return self._initial_state_lstm

    @property
    def cost_soft(self):
        return self._cost_soft
        
    @property
    def cost_lstm(self):
        return self._cost_lstm

    @property
    def final_state(self):
        return self._final_state

    @property
    def lr(self):
        return self._lr

    @property
    def train_op_soft(self):
        return self._train_op_soft
        
    @property
    def train_op_lstm(self):
        return self._train_op_lstm


class config_cbow(object):
    init_scale = FLAGS.init_scale
    learning_rate = FLAGS.learning_rate
    max_grad_norm = FLAGS.max_grad_norm
    num_layers = FLAGS.num_layers
    hidden_size = FLAGS.hidden_size
    max_epoch = FLAGS.max_epoch
    max_max_epoch = FLAGS.max_max_epoch
    keep_prob = FLAGS.keep_prob
    lr_decay = FLAGS.lr_decay
    batch_size = FLAGS.batch_size
    embedded_size_reg = FLAGS.embedded_size_reg
    embedded_size_cbow = FLAGS.embedded_size_cbow
    num_history = FLAGS.num_history
    vocab_size = 0
    unk_id = 0                      

def get_optimizer(lr):
    if FLAGS.optimizer == "GradDesc":
        return tf.train.GradientDescentOptimizer(lr)
    if FLAGS.optimizer == "Adadelta":
        return tf.train.AdadeltaOptimizer()
    if FLAGS.optimizer == "Adagrad":
        return tf.train.AdagradOptimizer(lr)
    if FLAGS.optimizer == "Momentum":
        return tf.train.MomentumOptimizer(lr,0.33)
    if FLAGS.optimizer == "Adam":
        return tf.train.AdamOptimizer()
    return 0

def get_loss_function(output, softmax_w, softmax_b, targets, batch_size, is_training,unk_id, vocab_size):
    
    #masking of 0 id's (always) and unk_id (only during testing)
    targets = tf.reshape(targets, [-1])
    mask = tf.logical_and(tf.not_equal(targets,[vocab_size]),tf.not_equal(targets,[unk_id]))
    mask2 = tf.reshape(tf.where(mask),[-1])
    targets = tf.gather(targets, mask2)
    output = tf.gather(output, mask2)
    nb_words_in_batch = tf.reduce_sum(tf.cast(mask,dtype=tf.float32)) + 1e-32

    if FLAGS.loss_function == "full_softmax":    
        logits = tf.matmul(output, softmax_w)
        loss = tf.nn.sparse_softmax_cross_entropy_with_logits(logits, targets, name=None)
        return tf.reduce_sum(loss) / nb_words_in_batch

    if FLAGS.loss_function == 'sampled_softmax':
        if is_training:
            loss = tf.nn.sampled_softmax_loss(tf.transpose(softmax_w), softmax_b, output, tf.reshape(targets, [-1,1]), 32, vocab_size)
            return tf.reduce_sum(loss) / nb_words_in_batch
        else:
            logits = tf.matmul(output, softmax_w)
            loss = tf.nn.sparse_softmax_cross_entropy_with_logits(logits, targets, name=None)
            return tf.reduce_sum(loss) / nb_words_in_batch

    return 0

def run_epoch(session, model, cost=None, eval_op=None, verbose=False, epoch_nb = 0):
    """Runs the model on the given data."""
    start_time = time.time()
    costs = 0.0
    iters = 0
    save_np = np.array([[0,0,0,0]])

    fetches = {}
    if eval_op is not None:
        fetches["eval_op"] = eval_op
    if cost is not None:
        fetches["cost"] = cost

    for step in range(model.input.epoch_size):
        vals = session.run(fetches)
        cost = vals["cost"]
        costs += cost
        iters += 1

        if verbose and step % (model.input.epoch_size // 10) == 0:
            print("%.3f perplexity: %.3f speed: %.0f wps" % (step * 1.0 / model.input.epoch_size, np.exp(costs / iters),
						 iters * model.input.batch_size * model.input.average_sentence_length / (time.time() - start_time)))
            save_np = np.append(save_np, [[epoch_nb, step * 1.0 / model.input.epoch_size, np.exp(costs / iters),
						 iters * model.input.batch_size * model.input.average_sentence_length / (time.time() - start_time)]],axis=0)
    save_np = np.append(save_np,[[epoch_nb, 1,np.exp(costs / iters),0]],axis=0)		 
    return np.exp(costs/iters), save_np[1:]

 
def main(_):
    print('job started')
    
    raw_data = reader_cbow_sentence.ds_raw_data(FLAGS.data_path)
    train_data, valid_data, test_data, vocab_size, unk_id, max_length, word_to_id  = raw_data 
    
    config = config_cbow()
    config.unk_id = vocab_size + 1
    config.vocab_size = vocab_size
    
    eval_config = config_cbow()
    eval_config.batch_size = 1
    eval_config.batch_size = 1
    eval_config.vocab_size = vocab_size
    eval_config.unk_id = unk_id
    
    with tf.Graph().as_default():
        initializer = tf.random_uniform_initializer(-config.init_scale, config.init_scale)
        tf.set_random_seed(1)

        with tf.name_scope("train"):
            train_input = ds_input(config=config, max_length=max_length, word_to_id=word_to_id, data=train_data, name="train_input")
            with tf.variable_scope("model", reuse=None, initializer=initializer):
                m = cbow_model(is_training=True, config=config, input_=train_input)
            #tf.scalar_summary("Training Loss", m.cost)
            #tf.scalar_summary("Learning Rate", m.lr)

        with tf.name_scope("valid"):
            valid_input = ds_input(config=config, max_length=max_length, word_to_id=word_to_id, data=valid_data, name="valid_input")
            with tf.variable_scope("model", reuse=True, initializer=initializer):
                mvalid = cbow_model(is_training=False, config=config, input_=valid_input)
            #tf.scalar_summary("Validation Loss", mvalid.cost)

        with tf.name_scope("test"):
            test_input = ds_input(config=eval_config, max_length=max_length, word_to_id=word_to_id, data=test_data, name="test_input")
            with tf.variable_scope("model", reuse=True, initializer=initializer):
                mtest = cbow_model(is_training=False, config=eval_config, input_=test_input)
				
        param_train_np = np.array([['init_scale',config.init_scale], ['learning_rate', config.learning_rate],
                                   ['max_grad_norm', config.max_grad_norm], ['num_layers', config.num_layers], ['num_history', config.num_history],
                                   ['hidden_size', config.hidden_size], 
                                   ['embedded_size_reg', config.embedded_size_reg],['embedded_size_cbow', config.embedded_size_cbow],
                                   ['max_epoch', config.max_epoch],
                                   ['max_max_epoch', config.max_max_epoch],['keep_prob', config.keep_prob], 
                                   ['lr_decay', config.lr_decay], ['batch_size', config.batch_size],
                                   ['vocab_size', vocab_size], ['optimizer', FLAGS.optimizer], 
                                   ['loss_function', FLAGS.loss_function],  ['cbow_position', FLAGS.position],  ['cbow_combination', FLAGS.combination]])
        train_np = np.array([[0,0,0,0]])
        valid_np = np.array([[0,0,0,0]])
		
        sv = tf.train.Supervisor(summary_writer=None,logdir=FLAGS.save_path + '/' + FLAGS.test_name + '_' + str(FLAGS.num_run))
        with sv.managed_session() as session:
            if FLAGS.position == 'soft':
                for i in range(config.max_max_epoch):
                    lr_decay = config.lr_decay ** max(i - config.max_epoch, 0.0)
                    m.assign_lr(session, config.learning_rate * lr_decay)
    				
                    print("Epoch: %d Learning rate: %.3f" % (i + 1, session.run(m.lr)))
    				
                    train_perplexity, tra_np = run_epoch(session, m, cost=m.cost_soft, eval_op=m.train_op_soft, verbose=True, epoch_nb=i)
                    print("Epoch: %d Train Perplexity: %.3f" % (i + 1, train_perplexity))
    				
                    valid_perplexity, val_np = run_epoch(session, mvalid, cost=mvalid.cost_soft, epoch_nb = i)
                    print("Epoch: %d Valid Perplexity: %.3f" % (i + 1, valid_perplexity))
    				
                    train_np = np.append(train_np, tra_np, axis=0)
                    valid_np= np.append(valid_np, val_np, axis=0)
                    		
                    #early stopping
                    early_stopping = 3; #new valid_PPL will be compared to the previous 3 valid_PPL: if it is bigger than the maximun of the 3 previous, it will stop
                    if i>early_stopping-1:
                        if valid_np[i+1][2] > np.max(valid_np[i+1-early_stopping:i],axis=0)[2]:
                            break
                
                test_perplexity, test_np = run_epoch(session, mtest, cost=mtest.cost_soft)
                print("Test Perplexity: %.3f" % test_perplexity)
            elif FLAGS.position == 'lstm':
                for i in range(config.max_max_epoch):
                    lr_decay = config.lr_decay ** max(i - config.max_epoch, 0.0)
                    m.assign_lr(session, config.learning_rate * lr_decay)
    				
                    print("Epoch: %d Learning rate: %.3f" % (i + 1, session.run(m.lr)))
    				
                    train_perplexity, tra_np = run_epoch(session, m, cost=m.cost_lstm, eval_op=m.train_op_lstm, verbose=True, epoch_nb=i)
                    print("Epoch: %d Train Perplexity: %.3f" % (i + 1, train_perplexity))
    				
                    valid_perplexity, val_np = run_epoch(session, mvalid, cost=mvalid.cost_lstm, epoch_nb = i)
                    print("Epoch: %d Valid Perplexity: %.3f" % (i + 1, valid_perplexity))
    				
                    train_np = np.append(train_np, tra_np, axis=0)
                    valid_np= np.append(valid_np, val_np, axis=0)
                    		
                    #early stopping
                    early_stopping = 3; #new valid_PPL will be compared to the previous 3 valid_PPL: if it is bigger than the maximun of the 3 previous, it will stop
                    if i>early_stopping-1:
                        if valid_np[i+1][2] > np.max(valid_np[i+1-early_stopping:i],axis=0)[2]:
                            break
                
                test_perplexity, test_np = run_epoch(session, mtest, cost=mtest.cost_lstm)
                print("Test Perplexity: %.3f" % test_perplexity)
            if FLAGS.save_path:
                print("Saving model to %s." % (FLAGS.save_path + '/' + FLAGS.test_name + '_' + str(FLAGS.num_run)  + '/' + FLAGS.test_name + '_' + str(FLAGS.num_run)))
                sv.saver.save(session, FLAGS.save_path + '/' + FLAGS.test_name + '_' + str(FLAGS.num_run) + '/' + FLAGS.test_name + '_'  + str(FLAGS.num_run), global_step=sv.global_step)
                np.savez((FLAGS.save_path + '/' + FLAGS.test_name + '_' + str(FLAGS.num_run)+ '/results' +'.npz'), param_train_np = param_train_np, train_np = train_np[1:], valid_np=valid_np[1:], test_np = test_np)

if __name__ == "__main__":
    tf.app.run()
