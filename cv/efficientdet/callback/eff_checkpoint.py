"""EFF Checkpoint Callback."""
import os
import shutil
import tempfile

import tensorflow as tf
from cv.efficientdet.utils.helper import encode_eff


class EffCheckpoint(tf.keras.callbacks.ModelCheckpoint):
    """Saves and, optionally, assigns the averaged weights.

    Attributes:
        See `tf.keras.callbacks.ModelCheckpoint` for the other args.
    """

    def __init__(self,
                 eff_dir: str,
                 key: str,
                 graph_only: bool = False,
                 monitor: str = 'val_loss',
                 verbose: int = 0,
                 save_best_only: bool = False,
                 save_weights_only: bool = False,
                 mode: str = 'auto',
                 save_freq: str = 'epoch',
                 **kwargs):

        super().__init__(
            eff_dir,
            monitor=monitor,
            verbose=verbose,
            save_best_only=save_best_only,
            save_weights_only=save_weights_only,
            mode=mode,
            save_freq=save_freq,
            **kwargs)
        self.eff_dir = eff_dir
        self.passphrase = key
        self.graph_only = graph_only

    def _remove_tmp_files(self):
        """Remove temporary zip file and directory."""
        shutil.rmtree(os.path.dirname(self.filepath))
        os.remove(self.temp_zip_file)

    def on_epoch_end(self, epoch, logs=None):
        """Override on_epoch_end."""
        self.epochs_since_last_save += 1
        epoch += 1 # eff name started with 001
        self.filepath = os.path.join(tempfile.mkdtemp(), f'ckpt-{epoch:03d}') # override filepath

        # pylint: disable=protected-access
        if self.save_freq == 'epoch' and self.epochs_since_last_save >= self.period:
            self._save_model(epoch=epoch, batch=None, logs=logs) # To self.filepath
            if self.graph_only:
                eff_filename = f"{self.model.name}.resume"
            else:
                eff_filename = f'{self.model.name}_{epoch:03d}.eff'
            eff_model_path = os.path.join(self.eff_dir, eff_filename)
            # convert content in self.filepath to EFF
            self.temp_zip_file = encode_eff(
                os.path.dirname(self.filepath),
                eff_model_path, self.passphrase)
            self._remove_tmp_files()
