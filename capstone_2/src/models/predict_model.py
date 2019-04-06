
import logging
import os
import numpy as np
from datetime import datetime
from src.models.data_manager import DataManager
from src.models.seqtoseq_model import SeqToSeqModel

# Function to predict SeqToSeq models


def predict_seqtoseq(question, model_name=None):
    """Calls into Seq2Seq Model for a response."""

    #
    # Configure logging
    #
    abs_path = os.path.abspath(os.path.dirname(__file__))
    logs_dir = os.path.join(abs_path, '../../logs')
    if not os.path.exists(logs_dir):
        os.mkdir(logs_dir)
        os.chmod(logs_dir, 0o777)
    log_path = os.path.join(abs_path, '../../logs/run-{0}.log')
    logging.basicConfig(filename=log_path.format(datetime.now().strftime('%Y%m%d-%H%M%S')),
                        level=logging.INFO,
                        format='%(asctime)s-%(process)d-%(name)s-%(levelname)s-%(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    logging.info('Seq2Seq Model Prediction started.')

    d = DataManager()

    # Convert Question to vocab tokens
    q_tokens = d.question_to_tokens(question)

    print(q_tokens)

    # Create a seq2seq Model instance
    model = SeqToSeqModel(model_name=model_name)

    # Make Prediction
    a_tokens = model.predict(q_tokens, d)

    print(a_tokens)

    # Convert answer to text
    answer = d.answer_from_tokens(np.trim_zeros(a_tokens, 'b'))

    print(answer)
    return answer


def predict_loop(model_name=None, num_turns=8):
    """Creates a chatbot loop."""
    for i in range(num_turns):
        print('Hello!')
        question = input('> ')
        if question == 'exit':
            print('Goodbye!')
            break
        answer = predict_seqtoseq(question, model_name=model_name)
        print(answer)


if __name__ == '__main__':
    predict_loop(model_name='test-seqtoseq')
