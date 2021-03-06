import logging
import time

import h2o
from h2o.automl import H2OAutoML

from automl.benchmark import TaskConfig
from automl.data import Dataset
from automl.results import NoResultError, save_predictions_to_file
from automl.utils import Timer

log = logging.getLogger(__name__)


def run(dataset: Dataset, config: TaskConfig):
    log.info("\n**** H2O AutoML ****\n")
    # Mapping of benchmark metrics to H2O metrics
    metrics_mapping = dict(
        acc='mean_per_class_error',
        auc='AUC',
        logloss='logloss',
        mae='mae',
        mse='mse',
        rmse='rmse',
        rmsle='rmsle'
    )
    sort_metric = metrics_mapping[config.metric] if config.metric in metrics_mapping else None
    if sort_metric is None:
        # TODO: Figure out if we are going to blindly pass metrics through, or if we use a strict mapping
        log.warning("Performance metric %s not supported, defaulting to AUTO.", config.metric)

    try:
        log.info("Starting H2O cluster with %s cores, %smb memory.", config.cores, config.max_mem_size_mb)
        h2o.init(nthreads=config.cores, max_mem_size=str(config.max_mem_size_mb) + "M")

        # Load train as an H2O Frame, but test as a Pandas DataFrame
        log.debug("Loading train data from %s.", dataset.train.path)
        train = h2o.import_file(dataset.train.path)
        # train.impute(method='mean')
        log.debug("Loading test data from %s.", dataset.test.path)
        test = h2o.import_file(dataset.test.path)
        # test.impute(method='mean')

        log.info("Running model on task %s, fold %s.", config.name, config.fold)
        log.debug("Running H2O AutoML with a maximum time of %ss on %s core(s), optimizing %s.",
                  config.max_runtime_seconds, config.cores, sort_metric)

        aml = H2OAutoML(max_runtime_secs=config.max_runtime_seconds,
                        sort_metric=sort_metric,
                        seed=config.seed,
                        **config.framework_params)

        with Timer() as training:
            aml.train(y=dataset.target.index, training_frame=train)

        if not aml.leader:
            raise NoResultError("H2O could not produce any model in the requested time.")

        log.debug("Leaderboard:\n%s", str(aml.leaderboard.as_data_frame()))

        preds = aml.predict(test).as_data_frame()
        # predictions = h2o.get_model(aml.leaderboard[0][1, 0]).predict(test).as_data_frame()

        y_pred = preds.iloc[:, 0]
        y_truth = test[:, dataset.target.index].as_data_frame(header=False)

        predictions = y_pred.values
        probabilities = preds.iloc[:, 1:].values

        save_predictions_to_file(dataset=dataset,
                                 output_file=config.output_predictions_file,
                                 probabilities=probabilities,
                                 predictions=predictions,
                                 truth=y_truth.values)

        return dict(
            models_count=len(aml.leaderboard),
            training_duration=training.duration
        )

    finally:
        if h2o.connection():
            h2o.remove_all()
            h2o.connection().close()
        # if h2o.cluster():
        #     h2o.cluster().shutdown()

