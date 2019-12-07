import os
import random
import yaml
import click
import pickle
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Activation
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.losses import mean_squared_error
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint



from src.timer import timer


@click.command()
@click.argument('mode')
@click.argument('input_filepath', type=click.Path(exists=True))
@click.argument('output_filepath', type=click.Path())
def main(mode, input_filepath, output_filepath):
    """
    Collects prepared data and starts training an CatBoost model. Parameters
    can be specified by editing src/config.yml.
    """
    random.seed(1337)
    with timer("Loading processed training data"):
        train_df, label = load_processed_training_data(input_filepath)

    with timer("One-Hot-Encode Categorical data"):
        cat_columns = list(train_df.select_dtypes(include=["category"]).columns)
        train_df = pd.get_dummies(train_df, columns=cat_columns)

    with timer("Scaling Data Frame"):
        scaler = StandardScaler()
        train_df = scaler.fit_transform(train_df)

        # Save scaler as it is needed for testing data as well
        with open('models/tf_cv/scaler.pkl', 'wb') as handle:
            pickle.dump(scaler, handle)


    ###########################################################################
    # BUILD TF MODEL                                                          #
    ###########################################################################
    with open("src/config.yml", 'r') as ymlfile:
        cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)

    layer_sizes = cfg["LAYER_SIZES"]
    splits = cfg["tf_splits_for_cv"]
    epochs = cfg["tf_epochs"]
    batch_size = cfg["tf_batch_size"]

    model = Sequential()

    model.add(Dense(layer_sizes[0], input_dim=train_df.shape[1]))
    model.add(Activation("relu"))

    if len(layer_sizes) > 1:
        for layer_size in layer_sizes[1:]:
            model.add(Dense(layer_size))
            model.add(Activation("relu"))

    model.add(Dense(1))
    model.add(Activation("linear"))

    model.compile(loss=mean_squared_error, optimizer=Adam)

    ###########################################################################

    if mode == "cv":
        start_cv_run(train_df, label, model, splits, epochs, batch_size, output_filepath)
    else:
        raise ValueError("Choose a valid mode: 'cv'")


def load_processed_training_data(input_filepath):
    """
    Loads processed data and returns a df with distinguished label
    column.
    """
    train_df = pd.read_pickle(input_filepath + "/train_data.pkl")

    label = np.log1p(train_df["meter_reading"])
    del train_df["meter_reading"]

    return train_df, label


def start_cv_run(train_df, label, model, splits, epochs, batch_size, output_filepath):
    """
    Starts a Cross Validation Run with the parameters provided.
    Scores will be documented and models will be saved.
    """
    output_filepath = output_filepath + "_cv"
    with timer("Performing " + str(splits) + " fold cross-validation"):
        kf = KFold(n_splits=splits, shuffle=False, random_state=1337)
        for i, (train_index, test_index) in enumerate(kf.split(train_df, label)):
            with timer("~~~~ Fold %d of %d ~~~~" % (i + 1, splits)):
                x_train, x_valid = train_df.iloc[train_index], train_df.iloc[test_index]
                y_train, y_valid = label[train_index], label[test_index]

                output_final = output_filepath + str(i) + ".h5"
                callbacks = [EarlyStopping(monitor="val_loss", patience=2),
                             ModelCheckpoint(filepath=output_final, monitor="val_loss", save_best_only=True)]

                model_instance = model.copy(deep=True)
                model_instance.fit(x_train,
                                   y_train,
                                   validation_data=(x_valid, y_valid),
                                   epochs=epochs,
                                   batch_size=batch_size,
                                   callbacks=callbacks)


if __name__ == "__main__":
    main()
