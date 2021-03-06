import tensorflow as tf 
from datasets import cifar10
from mymodel import *
import os 
import time
from datetime import datetime

slim = tf.contrib.slim 

##############################
# Flags most related to you #
##############################
tf.app.flags.DEFINE_integer(
    'batch_size', 64, 'The number of samples in each batch.')

tf.app.flags.DEFINE_integer(
    'epoch_number', 50,
    'Number of epoches')

#####################
# Dir Flags #
#####################
tf.app.flags.DEFINE_string(
    'checkpoint_path', None,
    'The path to a checkpoint from which to fine-tune.')

tf.app.flags.DEFINE_string(
    'train_dir', '/tmp/tfmodel/',
    'Directory where checkpoints and event logs are written to.')

tf.app.flags.DEFINE_string(
    'data_dir', '/tmp/tfdata/',
    'Directory of dataset.')

##############################
# Logs and Summaries Flags #
##############################
tf.app.flags.DEFINE_integer(
    'num_readers', 2,
    'The number of parallel readers that read data from the dataset.')

tf.app.flags.DEFINE_integer(
    'num_preprocessing_threads', 2,
    'The number of threads used to create the batches.')

tf.app.flags.DEFINE_integer(
    'log_every_n_steps', 30,
    'The frequency with which logs are print.')

tf.app.flags.DEFINE_integer(
    'summary_every_n_steps', 30,
    'The frequency with which summaries are saved, in seconds.')

tf.app.flags.DEFINE_integer(
    'save_interval_secs', 300,
    'The frequency with which the model is saved, in seconds.')

##############################
# Learning rate Flags #
##############################
tf.app.flags.DEFINE_float('learning_rate', 0.1, 'Initial learning rate.')

tf.app.flags.DEFINE_float(
    'learning_rate_decay_factor', 0.94, 'Learning rate decay factor.')

tf.app.flags.DEFINE_float(
    'num_epochs_per_decay', 2.0,
    'Number of epochs after which learning rate decays. Note: this flag counts '
    'epochs per clone but aggregates per sync replicas. So 1.0 means that '
    'each clone will go over full epoch individually, but replicas will go '
    'once across all replicas.')

FLAGS = tf.app.flags.FLAGS

def _configure_learning_rate(num_samples_per_epoch, global_step):

    decay_steps = int(num_samples_per_epoch * FLAGS.num_epochs_per_decay /
            FLAGS.batch_size)

    return tf.train.exponential_decay(FLAGS.learning_rate,
            global_step,
            decay_steps,
            FLAGS.learning_rate_decay_factor,
            staircase=True,
            name='exponential_decay_learning_rate')

# prepare images and lables for cifar10 dataset
dataset = cifar10.get_split('train', FLAGS.data_dir)
provider = slim.dataset_data_provider.DatasetDataProvider(
  dataset,
  num_readers=FLAGS.num_readers,
  common_queue_capacity=20 * FLAGS.batch_size,
  common_queue_min=10 * FLAGS.batch_size)
[image, label] = provider.get(['image', 'label'])

images, labels = tf.train.batch(
  [image, label],
  batch_size=FLAGS.batch_size,
  num_threads=FLAGS.num_preprocessing_threads,
  capacity=5 * FLAGS.batch_size)

labels = slim.one_hot_encoding(
  labels, dataset.num_classes)

batch_queue = slim.prefetch_queue.prefetch_queue(
  [images, labels], capacity=2)

images, labels = batch_queue.dequeue()
images = tf.cast(images, tf.float32)
# rerange images to [-4, 4], you can try other options
images = (images - 127) / 128 * 4

# configure learning rate and optimizer
global_step = tf.train.create_global_step()
learning_rate = _configure_learning_rate(dataset.num_samples, global_step)
optimizer = tf.train.GradientDescentOptimizer(learning_rate)
tf.summary.scalar('learning_rate', learning_rate)

model = Mymodel()
model.build(images, labels, train_mode=True)
loss = model.total_loss
acc = model.accuracy

grad = optimizer.compute_gradients(loss)
train_op = optimizer.apply_gradients(grad, global_step=global_step)
#train_op = optimizer.minimize(loss) #, global_step=global_step)

summaries = tf.get_collection(tf.GraphKeys.SUMMARIES)
summary_op = tf.summary.merge(summaries)
# summary_op = tf.summary.merge_all()

variables_to_save = tf.global_variables()
saver = tf.train.Saver(variables_to_save)

init = tf.global_variables_initializer()
init_local = tf.local_variables_initializer()

sess = tf.Session()
train_writer = tf.summary.FileWriter(FLAGS.train_dir + '/log', sess.graph)

sess.run(init)
sess.run(init_local)
tf.train.start_queue_runners(sess=sess)

epoch_steps = int(dataset.num_samples / FLAGS.batch_size)
print('number of steps each epoch: ', epoch_steps)
epoch_index = 0

max_steps = FLAGS.epoch_number * epoch_steps
ori_time = time.time()
next_save_time = FLAGS.save_interval_secs
for step in range(max_steps):
    start_time = time.time()
    if step % epoch_steps == 0:
        epoch_index += 1

    [_, loss_value, acc_value] = sess.run([train_op, loss, acc])

    duration = time.time() - start_time
    total_duration = time.time() - ori_time

    assert not np.isnan(loss_value), 'Model diverged with loss = NaN' 

    if step % FLAGS.log_every_n_steps == 0:
      examples_per_sec = FLAGS.batch_size / float(duration)
      format_str = ('Epoch %02d/%2d, %s: step %d, loss = %.6f accuracy = %.4f (%.1f examples/sec; %.3f ' 'sec/batch)')
      print(format_str % (epoch_index, FLAGS.epoch_number, datetime.now(), step, loss_value, acc_value[0],
          examples_per_sec, duration))

    if step % FLAGS.summary_every_n_steps == 0:
        summary_str = sess.run(summary_op)
        train_writer.add_summary(summary_str, step)

    if float(total_duration) > next_save_time:
        next_save_time += FLAGS.save_interval_secs
        checkpoint_path = os.path.join(FLAGS.train_dir, 'model.ckpt')
        save_path = saver.save(sess, checkpoint_path, global_step=global_step)
        print('saved model to %s' % save_path)

checkpoint_path = os.path.join(FLAGS.train_dir, 'model.ckpt')
save_path = saver.save(sess, checkpoint_path, global_step=global_step)
print('saved model to %s' % save_path)

