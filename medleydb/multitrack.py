#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Class definitions for MedleyDB multitracks."""

from __future__ import print_function

import csv
import os
import sox
import yaml

from . import INST_TAXONOMY
from . import INST_F0_TYPE
from . import MIXING_COEFFICIENTS
from . import ANNOT_PATH
from . import METADATA_PATH
from . import AUDIO_PATH

_YESNO = dict(yes=True, no=False)
_TRACKID_FMT = "%s_%s"
_METADATA_FMT = "%s_METADATA.yaml"
_STEMDIR_FMT = "%s_STEMS"
_RAWDIR_FMT = "%s_RAW"
_MIX_FMT = "%s_MIX.wav"
_STEM_FMT = "%s_STEM_%%s.wav"
_RAW_FMT = "%s_RAW_%%s_%%s.wav"

_AUDIODIR_FMT = "%s"

_ANNOTDIR_FMT = "%s_ANNOTATIONS"
_ACTIVCONF_FMT = "%s_ACTIVATION_CONF.lab"
_INTERVAL_FMT = "%s_INTERVALS.txt"
_MELODY1_FMT = "%s_MELODY1.csv"
_MELODY2_FMT = "%s_MELODY2.csv"
_MELODY3_FMT = "%s_MELODY3.csv"
_RANKING_FMT = "%s_RANKING.txt"
_SOURCEID_FMT = "%s_SOURCEID.lab"
_PITCHDIR_FMT = "%s_PITCH"
_PITCH_FMT = "%s.csv"


class MultiTrack(object):
    """MultiTrack Class definition.

    This class loads all available metadata, annotations, and filepaths for a
    given multitrack directory.

    Parameters
    ----------
    track_id : str
        Track id in format 'Artist_Title'.

    Attributes
    ----------
    artist : str
        The artist of the multitrack
    title : str
        The title of the multitrack
    track_id : str
        The unique identifier of the multitrack. In the form 'Artist_Title'
    annotation_dir : str
        Path to multitrack's annotation directory
    audio_path : str
        Path to multitrack's top level audio directory
    mix_path : str
        Path to multitrack's mix file.
    melody_rankings : dictionary
        Dictionary of melody rankings keyed by stem id
    mixing_coefficients : dictionary
        Dictionary of mixing weights keyed by stem id
    stems : dictionary
        Dictionary of stem Track objects keyed by stem id
    raw_audio : dictionary
        Dictionary of dictionaries keyed by stem id
    stem_instruments : list
        List of stem instrument labels
    raw_instruments : list
        List of raw audio instrument labels
    duration : float or None
        Duration of mix, or None if audio cannot be found
    is_excerpt : bool
        True if multitrack is an excerpt
    has_bleed : bool
        True if multitrack has bleed
    is_instrumental : bool
        True if multitrack is instrumental
    origin : str
        Origin of multitrack
    genre : str
        Genre of multitrack
    metadata_version : str
        Metadata version
    has_melody : bool
        True if multitrack has at least one melody stem
    predominant_stem : Track or None
        Track object for the predominant stem if availalbe, otherwise None
    stem_activations : np.array
        Matrix of stem activations
    stem_activations_idx : dictionary
        Dictionary mapping stem index to column of the stem_activations matrix
    _meta_path : str
        Path to metadata file.
    _pitch_path : str
        Path to multitrack's pitch annotation directory
    _stem_dir_path : str
        Path to multitrack's stem file directory
    _raw_dir_path : str
        Path to multitrack's raw file directory
    _stem_fmt : str
        Format of stem file basenames
    _raw_fmt : str
        format of raw file basenames
    _metadata : dict
        dictionary of data loaded from metadata file
    _melody_rankings_fpath : str
        Path to melody rankings file
    _melody1_annotation : np.array or None
        Melody 1 annotation if exists, otherwise None
    _melody2_annotation : np.array or None
        Melody 2 annotation if exists, otherwise None
    _melody3_annotation : np.array or None
        Melody 3 annotation if exists, otherwise None

    Examples
    --------
        >>> mtrack = Multitrack('LizNelson_Rainfall')
        >>> another_mtrack = Multitrack('ArtistName_TrackTitle')

    """

    def __init__(self, track_id):
        """MultiTrack object __init__ method.
        """

        # Artist, Title & Track Directory #
        self.artist = track_id.split('_')[0]
        self.title = track_id.split('_')[1]
        self.track_id = track_id

        # Filenames and Filepaths #
        self._meta_path = os.path.join(
            METADATA_PATH, _METADATA_FMT % self.track_id
        )

        # break if metadata file cannot be found
        if not os.path.exists(self._meta_path):
            raise IOError("Cannot find metadata for %s" % self.track_id)

        self.annotation_dir = os.path.join(
            ANNOT_PATH, _ANNOTDIR_FMT % self.track_id
        )
        self._pitch_path = os.path.join(
            self.annotation_dir, _PITCHDIR_FMT % self.track_id
        )

        if AUDIO_PATH:
            self.audio_path = os.path.join(
                AUDIO_PATH, _AUDIODIR_FMT % track_id
            )
            self._stem_dir_path = os.path.join(
                self.audio_path, _STEMDIR_FMT % self.track_id
            )
            self._raw_dir_path = os.path.join(
                self.audio_path, _RAWDIR_FMT % self.track_id
            )
            self.mix_path = os.path.join(
                self.audio_path, _MIX_FMT % self.track_id
            )
        else:
            self.audio_path = None
            self._stem_dir_path = None
            self._raw_dir_path = None
            self.mix_path = None

        # Stem & Raw File Formats #
        self._stem_fmt = _STEM_FMT % self.track_id
        self._raw_fmt = _RAW_FMT % self.track_id

        # Yaml Dictionary of Metadata #
        self._metadata = self._load_metadata()

        self._melody_rankings_fpath = os.path.join(
            self.annotation_dir, _RANKING_FMT % self.track_id
        )
        self.melody_rankings = self._get_melody_rankings()

        self.mixing_coefficients = MIXING_COEFFICIENTS[self.track_id]

        # Stem & Raw Dictionaries. Lists of filepaths. #
        self.stems, self.raw_audio = self._parse_metadata()

        # Lists of Instrument Labels #
        self.stem_instruments = sorted(
            [s.instrument for s in self.stems.values()]
        )
        self.raw_instruments = sorted(
            [r.instrument for r in get_dict_leaves(self.raw_audio)]
        )

        # Basic Track Information #
        if self.mix_path is not None and os.path.exists(self.mix_path):
            self.duration = get_duration(self.mix_path)
        else:
            print(("Warning: Audio missing for %s." % self.track_id))
            self.duration = None

        self.is_excerpt = _YESNO[self._metadata['excerpt']]
        self.has_bleed = _YESNO[self._metadata['has_bleed']]
        self.is_instrumental = _YESNO[self._metadata['instrumental']]
        self.origin = self._metadata['origin']
        self.genre = self._metadata['genre']
        self.metadata_version = self._metadata['version']

        mel1_path = os.path.join(self.annotation_dir,
                                 _MELODY1_FMT % self.track_id)
        self.has_melody = os.path.exists(mel1_path)

        self._melody1_annotation = None
        self._melody2_annotation = None
        self._melody3_annotation = None

        self.predominant_stem = self._get_predominant_stem()
        self.stem_activations, self.stem_activations_idx = \
            self._get_activation_annotations()

    @property
    def melody1_annotation(self):
        """np.array: Melody 1 annotation.
        """
        if self._melody1_annotation is None:
            melody1_fname = _MELODY1_FMT % self.track_id
            melody1_fpath = os.path.join(self.annotation_dir, melody1_fname)

            self._melody1_annotation, _ = read_annotation_file(
                melody1_fpath, header=False
            )
        return self._melody1_annotation

    @property
    def melody2_annotation(self):
        """np.array: Melody 2 annotation.
        """
        if self._melody2_annotation is None:
            melody2_fname = _MELODY2_FMT % self.track_id
            melody2_fpath = os.path.join(self.annotation_dir, melody2_fname)

            self._melody2_annotation, _ = read_annotation_file(
                melody2_fpath, header=False
            )
        return self._melody2_annotation

    @property
    def melody3_annotation(self):
        """np.array: Melody 3 annotation.
        """
        if self._melody3_annotation is None:
            melody3_fname = _MELODY3_FMT % self.track_id
            melody3_fpath = os.path.join(self.annotation_dir, melody3_fname)

            self._melody3_annotation, _ = read_annotation_file(
                melody3_fpath, header=False
            )
        return self._melody3_annotation

    def _load_metadata(self):
        """Load the metadata file.

        Returns
        -------
        metadata : dict
            Dictionary of data read directly from the YAML metadata file.

        """
        with open(self._meta_path, 'r') as f_in:
            metadata = yaml.load(f_in)
        return metadata

    def _parse_metadata(self):
        """Parse metadata dictionary.

        Returns
        -------
        stems : dict
            Dictionary of Track objects keyed by stem_id
        raw_audio : dict
            Dictionary of dictionaries of Track objects keyed by stem_id
            and raw_id

        """
        stems = dict()
        raw_audio = dict()
        stem_dict = self._metadata['stems']

        for k in stem_dict:
            stem_idx = int(k[1:])

            instrument = stem_dict[k]['instrument']
            component = stem_dict[k]['component']

            if stem_idx in self.melody_rankings:
                ranking = self.melody_rankings[stem_idx]
            else:
                ranking = None

            if AUDIO_PATH:
                file_name = stem_dict[k]['filename']
                file_path = os.path.join(self._stem_dir_path, file_name)
            else:
                file_path = None

            pitch_path = os.path.join(
                self._pitch_path,
                "%s_STEM_%s.csv" % (self.track_id, k[1:])
            )

            track = Track(instrument=instrument, file_path=file_path,
                          component=component, stem_idx=stem_idx,
                          ranking=ranking, mix_path=self.mix_path,
                          pitch_path=pitch_path,
                          mix_coeff=self.mixing_coefficients[stem_idx])

            stems[stem_idx] = track
            raw_dict = stem_dict[k]['raw']

            for j in raw_dict:
                raw_idx = int(j[1:])
                instrument = raw_dict[j]['instrument']

                if AUDIO_PATH:
                    file_name = raw_dict[j]['filename']
                    file_path = os.path.join(self._raw_dir_path, file_name)
                else:
                    file_path = None

                track = Track(instrument=instrument, file_path=file_path,
                              stem_idx=stem_idx, raw_idx=raw_idx,
                              mix_path=self.mix_path, ranking=ranking)
                if stem_idx not in raw_audio:
                    raw_audio[stem_idx] = {}

                raw_audio[stem_idx][raw_idx] = track

        return stems, raw_audio

    def _get_melody_rankings(self):
        """Get rankings from the melody rankings annotation file.

        Returns
        -------
        melody_rankings : dict
            Dictonary of melody rankings keyed by stem_id

        """
        melody_rankings = {}
        if os.path.exists(self._melody_rankings_fpath):
            with open(self._melody_rankings_fpath) as f_handle:
                linereader = csv.reader(f_handle)
                for line in linereader:
                    stem_idx = int(line[0].split('_')[-1].split('.')[0])
                    ranking = int(line[1])
                    melody_rankings[stem_idx] = ranking
        return melody_rankings

    def _get_predominant_stem(self):
        """Get predominant stem if files exists.
        
        Returns
        -------
        predominant_stem : Track or None
            If a predominant stem is labeled, returns the Track object
            corresponding to the predominant stem. Otherwise None.

        """

        if len(self.melody_rankings) > 0:
            predominant_idx = [
                k for k, v in self.melody_rankings.items() if v == 1
            ]
            if len(predominant_idx) > 0:
                predominant_idx = predominant_idx[0]
                return self.stems[predominant_idx]
            else:
                return None
        else:
            return None

    def _get_activation_annotations(self):
        """Get activation confidence annotation if file exists.

        Returns
        -------
        activations : list
            List of lists of activation confidences
        idx_dict : dict
            Dictionary of column ids in the activations table keyed by stem_id

        """
        fname = _ACTIVCONF_FMT % self.track_id
        activation_annotation_fpath = os.path.join(self.annotation_dir, fname)
        activations, header = read_annotation_file(
            activation_annotation_fpath, header=True
        )
        idx_dict = {}
        for i, stem_str in enumerate(header):
            if stem_str == 'time':
                continue
            else:
                stem_idx = format_index(stem_str)
                idx_dict[stem_idx] = i
        return activations, idx_dict

    def melody_stems(self):
        """Get list of stems that contain melody.

        Returns
        -------
        melody_stems : list
            List of Track objects where component='melody'.

        """
        stem_objects = self.stems.values()
        return [track for track in stem_objects if track.component == 'melody']

    def bass_stems(self):
        """Get list of stems that contain bass.

        Returns
        -------
        bass_stems: list
            List of Track objects where component='bass'.

        """
        stem_objects = self.stems.values()
        return [track for track in stem_objects if track.component == 'bass']

    def num_stems(self):
        """Number of stems.

        Returns
        -------
        n_stems : int
            Number of stems.

        """
        return len(self.stems)

    def num_raw(self):
        """Number of raw audio files.

        Returns
        -------
        n_raw : int
            Number of raw audio files.

        """
        return len(get_dict_leaves(self.raw_audio))

    def stem_filepaths(self):
        """Get list of filepaths to stem files.

        Returns
        -------
        stem_fpaths : list
            List of filepaths to stems.

        """
        return [track.file_path for track in self.stems.values()]

    def raw_filepaths(self):
        """Get list of filepaths to raw audio files.

        Returns
        -------
        raw_fpaths : list
            List of filepaths to raw audio files.

        """
        return [track.file_path for track in get_dict_leaves(self.raw_audio)]

    def activation_conf_from_stem(self, stem_idx):
        """Get activation confidence from given stem.

        Parameters
        ----------
        stem_idx : int
            stem index (eg. 2 for stem S02)

        Returns
        -------
        activation_confidence : list
            List of time, activation confidence pairs

        """
        activations = []
        if stem_idx in self.stem_activations_idx:
            activ_conf_idx = self.stem_activations_idx[stem_idx]
            for step in self.stem_activations:
                activations.append([step[0], step[activ_conf_idx]])
        else:
            activations = None

        return activations


class Track(object):
    """Track class definition.
    Used for stems and for raw audio tracks.

    Parameters
    ----------
    instrument : str
        The track's instrument label.
    file_path : str
        Path to corresponding audio file.
    stem_idx : int or str
        stem index, either as int or str
        For ArtistName_TrackTitle_STEM_05.wav, either 5 or 'S05'
    mix_path : str
        Path to corresponding mix audio file.
    pitch_path : str or None, default=None
        Path to pitch annotation directory
    raw_idx : int str or None, default=None
        Raw index, either as int or str
        For ArtistName_TrackTitle_RAW_05_02.wav, either 2 or 'R02'
    component : str, default=''
        stem's component label, if exists.
    ranking : int or None, default=None
        The Track's melodic ranking
    mix_coeff : float or None, default=None
        The Tracks's mixing coefficient

    Attributes
    ----------
    instrument : str
        The track's instrument label
    f0_type : str
        The track's f0 type. One of
            - 'm' for monophonic sources
            - 'p' for polyphonic sources
            - 'u' for unpitched sources
    file_path : str
        Path to corresponding audio file
    component : str or None
        The Track's component label, if exists
        E.g. 'melody', 'bass'
    ranking : int or None
        The Track's melodic ranking, if exists
    stem_idx : int
        The Track's stem index
    raw_idx : int or None
        The Track's raw index, if exists
    mixing_coefficient : float or None
        The Tracks's mixing coefficient, if exists
    duration : float or None
        The track's duration in seconds, if the audio is availalbe
    mix_path : str
        The path to the track's corresponding mix
    pitch_annotation : list or None
        List of pairs of time (seconds), frequency (Hz)
    _pitch_annotation : list or None
        List of pairs of time (seconds), frequency (Hz)
    _pitch_path : str or None
        Path to pitch annotation file, if exists

    """

    def __init__(self, instrument, file_path, stem_idx, mix_path,
                 pitch_path=None, raw_idx=None, component='', ranking=None,
                 mix_coeff=None):
        """Track object __init__ method.
        """
        self.instrument = instrument
        self.f0_type = get_f0_type(instrument)
        self.file_path = file_path
        self.component = component
        self.ranking = ranking
        self.stem_idx = format_index(stem_idx)
        self.raw_idx = format_index(raw_idx)
        self.mixing_coefficient = mix_coeff

        if file_path is not None and os.path.exists(file_path):
            self.duration = get_duration(file_path)
        else:
            self.duration = None
        self.mix_path = mix_path
        self._pitch_annotation = None
        self._pitch_path = pitch_path

    @property
    def pitch_annotation(self):
        """list: List of pairs of time (seconds), frequency (Hz)
        """
        if (self._pitch_path is not None) and (self._pitch_annotation is None):
            self._pitch_annotation, _ = read_annotation_file(
                self._pitch_path, num_cols=2, header=False
            )
        return self._pitch_annotation

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        return self.__dict__ != other.__dict__

    def __hash__(self):
        return hash((self.instrument,
                     self.file_path,
                     self.component,
                     self.stem_idx,
                     self.raw_idx,
                     self.mix_path,
                     self._pitch_path))


def get_f0_type(instrument):
    """Get the f0 type of an instrument.

    Parameters
    ----------
    instrument : str
        Instrument label, e.g. 'flute'

    Returns
    -------
    f0_type : str
        The instrument's f0 type. One of
            - 'm' for monophonic sources
            - 'p' for polyphonic sources
            - 'u' for unpitched sources

    """
    if instrument in set(INST_F0_TYPE.keys()):
        return INST_F0_TYPE[instrument]
    else:
        return "?"


def _path_basedir(path):
    """Get the name of the lowest directory of a path.

    Parameters
    ----------
    path : str
        A file path.

    Returns
    -------
    basedir : str
        The base directory of a path

    """
    return os.path.basename(os.path.normpath(path))


def format_index(index):
    """Load stem or raw index. Reformat if in string form.
    
    Parameters
    ----------
    index : int or str
        Index in string or integer form.
        E.g. any of 1 or 'S01' or 'R01'

    Returns
    -------
    formatted_index : int
        Index in integer form

    """
    if isinstance(index, str):
        return int(index.strip('S').strip('R'))
    elif index is None:
        return None
    else:
        return int(index)


def get_dict_leaves(dictionary):
    """Get the set of all leaves of a dictionary.

    Parameters
    ----------
    dictionary : dict
        A dictionary or nested dictionary.

    Returns
    -------
    vals : set
        Set of leaf values.

    """
    vals = []
    if isinstance(dictionary, dict):
        for k in dictionary:
            if isinstance(dictionary[k], dict):
                for val in get_dict_leaves(dictionary[k]):
                    vals.append(val)
            else:
                if hasattr(dictionary[k], '__iter__'):
                    for val in dictionary[k]:
                        vals.append(val)
                else:
                    vals.append(dictionary[k])
    else:
        for val in dictionary:
            vals.append(val)

    return set(vals)


def get_duration(wave_fpath):
    """Get the duration of a wave file, in seconds.

    Parameters
    ----------
    wave_fpath : str
        Wave file.

    Returns
    -------
    duration : float
        Duration of wave file in seconds.

    """
    n_samples = float(sox.file_info.num_samples(wave_fpath))
    sample_rate = float(sox.file_info.sample_rate(wave_fpath))
    return n_samples / sample_rate


def read_annotation_file(fpath, num_cols=None, header=False):
    """Read an annotation file.
    The returned annotations can be directly converted to a numpy array,
    if desired.

    When reading files generated by Tony, set num_cols=2.
    Annotation files created by Tony can contain a third column that
    sometimes has a value (e.g [2]) and sometimes does not. It isn't
    important for annotation and can be ignored.

    Parameters
    ----------
    fpath : str
        Path to annotation file.
    num_cols : int or None, default=None
        Number of columns to read. If specified,
        will only read the return num_cols columns of the annotation file.

    Returns
    -------
    annotation : list
        List of rows of the annotation file.
    header : list
        Header row. Empty list if header=False.

    Examples
    --------
    >>> melody_fpath = 'ArtistName_TrackTitle_MELODY1.txt'
    >>> pitch_fpath = 'my_tony_pitch_annotation.csv'
    >>> melody_annotation, _ = read_annotation_file(melody_fpath)
    >>> activation_annotation, header = read_annotation_file(
            actvation_fpath, header=True
        )
    >>> pitch_annotation, _ = read_annotation_file(pitch_fpath, num_cols=2)

    """
    if os.path.exists(fpath):
        with open(fpath) as f_handle:
            annotation = []
            linereader = csv.reader(f_handle)

            # skip the headers for non csv files
            if header:
                header = next(linereader)
            else:
                header = []

            for line in linereader:
                if num_cols:
                    line = line[:num_cols]
                annotation.append([float(val) for val in line])
        return annotation, header
    else:
        print("Warning: %s does not exist." % fpath)
        return None, None


def get_valid_instrument_labels(taxonomy=INST_TAXONOMY):
    """Get set of valid instrument labels based on a taxonomy.

    Parameters
    ----------
    taxonomy_file : str, default=INST_TAXONOMY
        Path to instrument taxonomy file.

    Returns
    -------
    valid_instrument_labels : set
        Set of valid instrument labels.

    Examples
    --------
    >>> valid_labels = get_valid_instrument_labels()
    >>> my_valid_labels = get_valid_instrument_labels('my_taxonomy.yaml')

    """
    valid_instrument_labels = get_dict_leaves(taxonomy)
    return valid_instrument_labels


def is_valid_instrument(instrument):
    """Test if an instrument is valid based on a taxonomy.
    This is case sensitive! Taxonomy instrument labels are all lowercase.

    Parameters
    ----------
    instrument : str
        Input instrument.

    Returns
    -------
    value : bool
        True if instrument is valid.

    Examples
    --------
    >>> is_valid_instrument('clarinet')
    True
    >>> is_valid_instrument('Clarinet')
    False
    >>> is_valid_instrument('mayonnaise')
    False

    """
    return instrument in get_valid_instrument_labels()
