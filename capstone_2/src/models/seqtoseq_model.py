
# from sklearn.base import BaseEstimator
import logging
import numpy as np
import tensorflow as tf
import time

#
# Sequence to Sequence Model
# LSTM based model with Attention
#


class SeqToSeqModel:
    """Implementation of the Sequence to Sequence model."""

    def __init__(self,
                 epochs=100,
                 batch_size=128,
                 rnn_size=512,
                 num_layers=2,
                 encoding_embedding_size=512,
                 decoding_embedding_size=512,
                 learning_rate=0.005,
                 learning_rate_decay=0.9,
                 min_learning_rate=0.0001,
                 keep_probability=0.75,
                 model_name=None
                 ):

        # Model Parameters
        # Number of epochs
        self.epochs = epochs

        # Batch size
        self.batch_size = batch_size

        # Number of units in LSTM cell
        self.rnn_size = rnn_size

        # Number of RNN Layers
        self.num_layers = num_layers

        # Encoder embedding size
        self.encoding_embedding_size = encoding_embedding_size

        # Decoder embedding size
        self.decoding_embedding_size = decoding_embedding_size

        # Learning rate
        self.learning_rate = learning_rate

        # Learning rate decay
        self.learning_rate_decay = learning_rate_decay

        # Minimum Learning rate
        self.min_learning_rate = min_learning_rate

        # Keep probability
        self.keep_probability = keep_probability

        # Model Name
        self.model_name = model_name

        logging.info('Model SeqtoSeq Initialization completed.')

    def fit(self, sorted_questions, sorted_answers, questions_int_to_vocab, answers_int_to_vocab):
        """Training model."""

        # Create dictionaries to map the unique integers to their respective words.
        # i.e. an inverse dictionary for vocab_to_int.
        questions_vocab_to_int = {v_i: v for v, v_i in questions_int_to_vocab.items()}
        answers_vocab_to_int = {v_i: v for v, v_i in answers_int_to_vocab.items()}

        # Reset the graph to ensure that it is ready for training
        tf.reset_default_graph()

        # Start the session
        with tf.Session() as sess:

            # Load the model inputs
            input_data, targets, lr = self.model_inputs()

            # Sequence length will be the max line length for each batch
            # sequence_length = tf.placeholder_with_default(max_line_length, None, name='sequence_length')
            sequence_length = tf.placeholder(tf.int32, shape=[self.batch_size], name="sequence_length")

            # Find the shape of the input data for sequence_loss
            input_shape = tf.shape(input_data)

            # Create the training and inference logits
            train_logits, inference_logits = self.seq2seq_model(
                tf.reverse(input_data, [-1]), targets, self.batch_size, sequence_length,
                len(answers_vocab_to_int),
                len(questions_vocab_to_int),
                self.encoding_embedding_size,
                self.decoding_embedding_size,
                self.rnn_size,
                self.num_layers,
                questions_vocab_to_int)

            # Create a tensor for the inference logits, needed if loading a checkpoint version of the model
            tf.identity(inference_logits, 'logits')

            with tf.name_scope("optimization"):
                # Loss function
                cost = tf.contrib.seq2seq.sequence_loss(
                    train_logits,
                    targets,
                    tf.ones_like(targets, dtype=tf.float32))

                # Optimizer
                optimizer = tf.train.AdamOptimizer(self.learning_rate)

                # Gradient Clipping
                gradients = optimizer.compute_gradients(cost)
                capped_gradients = [
                    (tf.clip_by_value(grad, -5., 5.), var) for grad, var in gradients if grad is not None]
                train_op = optimizer.apply_gradients(capped_gradients)

            # Validate the training with 10% of the data
            train_valid_split = int(len(sorted_questions) * 0.15)

            # Split the questions and answers into training and validating data
            train_questions = sorted_questions[train_valid_split:]
            train_answers = sorted_answers[train_valid_split:]

            valid_questions = sorted_questions[:train_valid_split]
            valid_answers = sorted_answers[:train_valid_split]

            # Check training loss after every 100 batches
            display_step = 100

            # Early Stop Initialization
            stop_early = 0

            # If the validation loss does decrease in 5 consecutive checks, stop training
            stop = 5

            # Modulus for checking validation loss
            validation_check = ((len(train_questions)) // self.batch_size // 2) - 1

            # Record the training loss for each display step
            total_train_loss = 0

            # Record the validation loss for saving improvements in the model
            summary_valid_loss = []
            learning_rate = self.learning_rate

            checkpoint = "best_model.ckpt"

            sess.run(tf.global_variables_initializer())

            for epoch_i in range(1, self.epochs + 1):
                for batch_i, (questions_batch, answers_batch, sequence_length_batch) in enumerate(
                        self.batch_data(train_questions,
                                        train_answers, self.batch_size, questions_vocab_to_int, answers_vocab_to_int)):
                    start_time = time.time()
                    _, loss = sess.run(
                        [train_op, cost],
                        {input_data: questions_batch,
                         targets: answers_batch,
                         lr: learning_rate,
                         sequence_length: sequence_length_batch})

                    total_train_loss += loss
                    end_time = time.time()
                    batch_time = end_time - start_time

                    if batch_i % display_step == 0:
                        print('Epoch {:>3}/{} Batch {:>4}/{} - Loss: {:>6.3f}, Seconds: {:>4.2f}'
                              .format(epoch_i,
                                      self.epochs,
                                      batch_i,
                                      len(train_questions) // self.batch_size,
                                      total_train_loss / display_step,
                                      batch_time * display_step))
                        total_train_loss = 0

                    if batch_i % validation_check == 0 and batch_i > 0:
                        total_valid_loss = 0
                        start_time = time.time()
                        for batch_ii, (questions_batch_ii, answers_batch_ii, sequence_length_batch_ii) in \
                                enumerate(self.batch_data(valid_questions, valid_answers, self.batch_size,
                                                          questions_vocab_to_int, answers_vocab_to_int)):
                            valid_loss = sess.run(
                                cost, {input_data: questions_batch_ii,
                                       targets: answers_batch_ii,
                                       lr: learning_rate,
                                       sequence_length: sequence_length_batch_ii})
                            total_valid_loss += valid_loss
                        end_time = time.time()
                        batch_time = end_time - start_time
                        avg_valid_loss = total_valid_loss / (len(valid_questions) / self.batch_size)
                        print('Valid Loss: {:>6.3f}, Seconds: {:>5.2f}'.format(avg_valid_loss, batch_time))

                        # Reduce learning rate, but not below its minimum value
                        learning_rate *= self.learning_rate_decay
                        if learning_rate < self.min_learning_rate:
                            learning_rate = self.min_learning_rate

                        summary_valid_loss.append(avg_valid_loss)
                        if avg_valid_loss <= min(summary_valid_loss):
                            print('New Record!')
                            stop_early = 0
                            saver = tf.train.Saver()
                            saver.save(sess, checkpoint)

                        else:
                            print("No Improvement.")
                            stop_early += 1
                            if stop_early == stop:
                                break

                if stop_early == stop:
                    print("Stopping Training.")
                    break

        return

    def predict(self, question):
        pass

    @staticmethod
    def model_inputs():
        """Create placeholders for inputs to the model"""

        # Question
        input_data = tf.placeholder(tf.int32, [None, None], name='input')

        # Response
        targets = tf.placeholder(tf.int32, [None, None], name='targets')

        # Learning Rate
        lr = tf.placeholder(tf.float32, name='learning_rate')

        return input_data, targets, lr

    @staticmethod
    def process_encoding_input(target_data, vocab_to_int, batch_size):
        """Remove the last word id from each batch and concat the <GO> to the begining of each batch"""
        ending = tf.strided_slice(target_data, [0, 0], [batch_size, -1], [1, 1])
        dec_input = tf.concat([tf.fill([batch_size, 1], vocab_to_int['<GO>']), ending], 1)

        return dec_input

    @staticmethod
    def encoding_layer(rnn_inputs, rnn_size, num_layers, keep_prob, sequence_length):
        """Create the encoding layer"""

        lstm = tf.contrib.rnn.BasicLSTMCell(rnn_size)
        drop = tf.contrib.rnn.DropoutWrapper(lstm, input_keep_prob=keep_prob)
        enc_cell = tf.contrib.rnn.MultiRNNCell([drop] * num_layers)
        enc_output, enc_state = tf.nn.bidirectional_dynamic_rnn(
            cell_fw=enc_cell,
            cell_bw=enc_cell,
            sequence_length=sequence_length,
            inputs=rnn_inputs,
            dtype=tf.float32)

        return enc_output, enc_state

    @staticmethod
    def decoding_layer_train(encoder_state, dec_cell, dec_embed_input, sequence_length, decoding_scope,
                             output_fn, keep_prob, batch_size):
        """Decode the training data"""

        attention_states = tf.zeros([batch_size, 1, dec_cell.output_size])

        att_keys, att_vals, att_score_fn, att_construct_fn = \
            tf.contrib.seq2seq.prepare_attention(attention_states,
                                                 attention_option="bahdanau",
                                                 num_units=dec_cell.output_size)

        train_decoder_fn = tf.contrib.seq2seq.attention_decoder_fn_train(encoder_state[0],
                                                                      att_keys,
                                                                      att_vals,
                                                                      att_score_fn,
                                                                      att_construct_fn,
                                                                      name="attn_dec_train")
        train_pred, _, _ = tf.contrib.seq2seq.dynamic_rnn_decoder(dec_cell,
                                                                  train_decoder_fn,
                                                                  dec_embed_input,
                                                                  sequence_length,
                                                                  scope=decoding_scope)
        train_pred_drop = tf.nn.dropout(train_pred, keep_prob)
        return output_fn(train_pred_drop)

    @staticmethod
    def decoding_layer_infer(encoder_state, dec_cell, dec_embeddings, start_of_sequence_id, end_of_sequence_id,
                             maximum_length, vocab_size, decoding_scope, output_fn, batch_size):
        """Decode the prediction data"""

        attention_states = tf.zeros([batch_size, 1, dec_cell.output_size])

        att_keys, att_vals, att_score_fn, att_construct_fn = \
            tf.contrib.seq2seq.prepare_attention(attention_states,
                                                 attention_option="bahdanau",
                                                 num_units=dec_cell.output_size)

        infer_decoder_fn = tf.contrib.seq2seq.attention_decoder_fn_inference(output_fn,
                                                                             encoder_state[0],
                                                                             att_keys,
                                                                             att_vals,
                                                                             att_score_fn,
                                                                             att_construct_fn,
                                                                             dec_embeddings,
                                                                             start_of_sequence_id,
                                                                             end_of_sequence_id,
                                                                             maximum_length,
                                                                             vocab_size,
                                                                             name="attn_dec_inf")
        infer_logits, _, _ = tf.contrib.seq2seq.dynamic_rnn_decoder(dec_cell,
                                                                    infer_decoder_fn,
                                                                    scope=decoding_scope)

        return infer_logits

    def decode(self, vocab_size, sequence_length, encoder_output, encoder_state, helper, scope, reuse=None):

        with tf.variable_scope(scope, reuse=reuse):
            lstm = tf.contrib.rnn.BasicLSTMCell(self.rnn_size)
            drop = tf.contrib.rnn.DropoutWrapper(lstm, input_keep_prob=self.keep_probability)
            dec_cell = tf.contrib.rnn.MultiRNNCell([drop] * self.num_layers)

            num_units = dec_cell.output_size

            # Create Attention Mechanism
            # attention_mechanism = tf.contrib.seq2seq.BahdanauAttention(
            #    num_units=num_units, memory=tf.transpose(tf.concat(encoder_output, -1), [1, 0, 2]), normalize=True)

            # attn_cell = tf.contrib.seq2seq.AttentionWrapper(
            #    dec_cell, attention_mechanism, output_attention=False)

            # attention_zero = attn_cell.zero_state(batch_size=self.batch_size, dtype=tf.float32)

            # alternatively concat forward and backward states
            bi_encoder_state = []
            for layer_id in range(self.num_layers):
                bi_encoder_state.append(encoder_state[0][layer_id])  # forward
                # bi_encoder_state.append(encoder_state[1][layer_id])  # backward

            bi_encoder_state = tuple(bi_encoder_state)

            # concatenate c1 and c2 from encoder final states
            # new_c = tf.concat([encoder_state[0][0].c, encoder_state[0][1].c], axis=1)

            # concatenate h1 and h2 from encoder final states
            # new_h = tf.concat([encoder_state[0][0].h, encoder_state[0][1].h], axis=1)

            # define initial state using concatenated h states and c states
            # init_state = attention_zero.clone(cell_state=tf.contrib.rnn.LSTMStateTuple(c=new_c, h=new_h))
            # init_state = attention_zero.clone(cell_state=bi_encoder_state)

            # out_cell = tf.contrib.rnn.OutputProjectionWrapper(
            #     attn_cell, vocab_size, reuse=reuse
            # )
            projection_layer = tf.layers.Dense(vocab_size, use_bias=True, bias_initializer=tf.zeros_initializer())

            decoder = tf.contrib.seq2seq.BasicDecoder(
                cell=dec_cell,
                helper=helper,
                initial_state=bi_encoder_state,
                output_layer=projection_layer
            )

            final_outputs, _final_state, _final_sequence_lengths = tf.contrib.seq2seq.dynamic_decode(
                decoder=decoder,
                impute_finished=True
            )

            logits = final_outputs.rnn_output

            return logits

    def decoding_layer(self, dec_embed_input, dec_embeddings, encoder_output, encoder_state, vocab_size,
                       sequence_length, rnn_size, num_layers, vocab_to_int, keep_prob, batch_size):
        """Create the decoding cell and input the parameters for the training and inference decoding layers"""

        start_of_sequence_id = vocab_to_int['<GO>']
        start_tokens = tf.fill([batch_size], start_of_sequence_id)
        end_of_sequence_id = vocab_to_int['<EOS>']

        train_helper = tf.contrib.seq2seq.TrainingHelper(dec_embed_input, sequence_length)
        infer_helper = tf.contrib.seq2seq.GreedyEmbeddingHelper(dec_embeddings,
                                                                start_tokens=tf.to_int32(start_tokens),
                                                                end_token=end_of_sequence_id)

        with tf.variable_scope("decoding") as decoding_scope:

            # weights = tf.truncated_normal_initializer(stddev=0.1)
            # biases = tf.zeros_initializer()
            #
            # def output_fn(x):
            #     return tf.contrib.layers.fully_connected(x,
            #                                              vocab_size,
            #                                              None,
            #                                              scope=decoding_scope,
            #                                              weights_initializer=weights,
            #                                              biases_initializer=biases)
            #
            train_logits = self.decode(
                vocab_size, sequence_length, encoder_output, encoder_state, train_helper, 'scope')

            decoding_scope.reuse_variables()

            infer_logits = self.decode(
                vocab_size, sequence_length, encoder_output, encoder_state, infer_helper, 'scope',
                reuse=True)

            # train_logits = self.decoding_layer_train(encoder_state,
            #                                          dec_cell,
            #                                          dec_embed_input,
            #                                          sequence_length,
            #                                          decoding_scope,
            #                                          output_fn,
            #                                          keep_prob,
            #                                          batch_size)
            # decoding_scope.reuse_variables()
            # infer_logits = self.decoding_layer_infer(encoder_state,
            #                                          dec_cell,
            #                                          dec_embeddings,
            #                                          vocab_to_int['<GO>'],
            #                                          vocab_to_int['<EOS>'],
            #                                          sequence_length - 1,
            #                                          vocab_size,
            #                                          decoding_scope,
            #                                          output_fn,
            #                                          batch_size)

        return train_logits, infer_logits

    def seq2seq_model(self, input_data, target_data, batch_size, sequence_length, answers_vocab_size,
                      questions_vocab_size, enc_embedding_size, dec_embedding_size, rnn_size, num_layers,
                      questions_vocab_to_int):
        """Use the previous functions to create the training and inference logits"""

        enc_embed_input = tf.contrib.layers.embed_sequence(input_data,
                                                           answers_vocab_size + 1,
                                                           enc_embedding_size,
                                                           initializer=tf.random_uniform_initializer(0, 1))
        enc_output, enc_state = self.encoding_layer(
            enc_embed_input, rnn_size, num_layers, self.keep_probability, sequence_length)

        dec_input = self.process_encoding_input(target_data, questions_vocab_to_int, batch_size)
        dec_embeddings = tf.Variable(tf.random_uniform([questions_vocab_size + 1, dec_embedding_size], 0, 1))
        dec_embed_input = tf.nn.embedding_lookup(dec_embeddings, dec_input)

        train_logits, infer_logits = self.decoding_layer(dec_embed_input,
                                                         dec_embeddings,
                                                         enc_output,
                                                         enc_state,
                                                         questions_vocab_size,
                                                         sequence_length,
                                                         rnn_size,
                                                         num_layers,
                                                         questions_vocab_to_int,
                                                         self.keep_probability,
                                                         batch_size)
        return train_logits, infer_logits

    @staticmethod
    def pad_sentence_batch(sentence_batch, vocab_to_int):
        """Pad sentences with <PAD> so that each sentence of a batch has the same length"""
        max_sentence = max([len(sentence) for sentence in sentence_batch])
        return [sentence + [vocab_to_int['<PAD>']] * (max_sentence - len(sentence)) for sentence in sentence_batch]

    def batch_data(self, questions, answers, batch_size, questions_vocab_to_int, answers_vocab_to_int):
        """Batch questions and answers together"""
        for batch_i in range(0, len(questions) // batch_size):
            start_i = batch_i * batch_size
            questions_batch = questions[start_i:start_i + batch_size]
            answers_batch = answers[start_i:start_i + batch_size]
            sequence_length_batch = [len(answer) for answer in answers_batch]
            pad_questions_batch = np.array(self.pad_sentence_batch(questions_batch, questions_vocab_to_int))
            pad_answers_batch = np.array(self.pad_sentence_batch(answers_batch, answers_vocab_to_int))
            yield pad_questions_batch, pad_answers_batch, sequence_length_batch
