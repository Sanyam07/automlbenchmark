import numpy as np
from sklearn.base import TransformerMixin
from sklearn.preprocessing import LabelEncoder, LabelBinarizer, OneHotEncoder

try:
    from sklearn.preprocessing import OrdinalEncoder
except ImportError:
    from sklearn.preprocessing import LabelEncoder as OrdinalEncoder


class Encoder(TransformerMixin):

    def __init__(self, type='label', target=True, encoded_type=float,
                 missing_handle='ignore', missing_values=None, missing_replaced_by=''):
        """

        :param type:
        :param target:
        :param missing_handle: one of ['ignore', 'mask', 'encode'].
            ignore: use only if there's no missing value for sure data to be transformed, otherwise it may raise an error during transform()
            mask: replace missing values only internally
            encode: encode all missing values as the encoded value of missing_replaced_by
        :param missing_values:
        :param missing_replaced_by:
        """
        super().__init__()
        assert missing_handle in ['ignore', 'mask', 'encode']
        self.for_target = target
        self.missing_handle = missing_handle
        self.missing_values = set(missing_values).union([None]) if missing_values else {None}
        self.missing_replaced_by = missing_replaced_by
        self.missing_encoded_value = None
        self.encoded_type = int if target else encoded_type
        self.str_encoder = None
        self.classes = None
        self._enc_classes_ = None
        if type == 'label':
            self.delegate = LabelEncoder() if target else OrdinalEncoder()
        elif type == 'one-hot':
            self.str_encoder = None if target else OrdinalEncoder()
            self.delegate = LabelBinarizer() if target else OneHotEncoder(handle_unknown='ignore')
        elif type == 'no-op':
            self.delegate = None
        else:
            raise ValueError("encoder type should be one of {}".format(['label', 'one-hot']))

    @property
    def _ignore_missing(self):
        return self.for_target or self.missing_handle == 'ignore'

    @property
    def _mask_missing(self):
        return not self.for_target and self.missing_handle == 'mask'

    @property
    def _encode_missing(self):
        return not self.for_target and self.missing_handle == 'encode'

    def fit(self, vec):
        if not self.delegate:
            return self

        self.classes = np.unique(vec) if self._ignore_missing else np.unique(np.insert(vec, 0, self.missing_replaced_by))
        self._enc_classes_ = self.str_encoder.fit_transform(self.classes) if self.str_encoder else self.classes

        if self._mask_missing:
            self.missing_encoded_value = self.delegate.fit_transform(self.classes)[0]
        else:
            self.delegate.fit(self.classes)
        return self

    def transform(self, vec, **params):
        if not self.delegate:
            return vec

        return_value = lambda v: v
        if isinstance(vec, str):
            vec = [vec]
            return_value = (lambda v: v[0])

        if self.str_encoder:
            vec = self.str_encoder.transform(vec)

        if self._mask_missing or self._encode_missing:
            mask = [v in self.missing_values for v in vec]
            if any(mask):
                nvec = vec if isinstance(vec, np.ndarray) else np.array(vec)
                if self._mask_missing:
                    missing = nvec[mask]
                nvec[mask] = self.missing_replaced_by
                res = self.delegate.transform(nvec, **params)
                if self._mask_missing and self.encoded_type != int:
                    if None in missing:
                        res = res.astype(self.encoded_type)
                    res[mask] = np.NaN if self.encoded_type == float else None
                return return_value(res)

        return return_value(self.delegate.transform(vec, **params))

    def inverse_transform(self, vec, **params):
        if not self.delegate:
            return vec

        # todo handle mask
        return self.delegate.inverse_transform(vec, **params)
