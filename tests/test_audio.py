import io
import json
import subprocess

import pytest
from mutagen.mp3 import EasyMP3
from mutagen.oggopus import OggOpus

import madam.audio
from madam.core import OperatorError, UnsupportedFormatError
from madam.future import subprocess_run
from assets import audio_asset, mp3_asset, opus_asset, wav_asset, nut_audio_asset, unknown_asset


class TestMutagenProcessor:
    @pytest.fixture(name='processor')
    def mutagen_processor(self):
        return madam.audio.MutagenProcessor()

    def test_create_asset_from_mp3(self, processor):
        mp3_file_path = 'tests/resources/64kbits_with_id3v2-4.mp3'
        with open(mp3_file_path, 'rb') as mp3_file:
            asset = processor._read(mp3_file)
        assert asset.mime_type == 'audio/mpeg'
        assert asset.duration == pytest.approx(0.144, abs=0.01)
        assert asset.essence is not None
        assert asset.essence.read()

    def test_mp3_reader_does_not_change_file(self, processor):
        mp3_file_path = 'tests/resources/64kbits.mp3'
        with open(mp3_file_path, 'rb') as mp3_file:
            expected_data = mp3_file.read()
        with open(mp3_file_path, 'rb') as mp3_file:
            processor._read(mp3_file)
        with open(mp3_file_path, 'rb') as mp3_file:
            actual_data = mp3_file.read()
        assert expected_data == actual_data


class TestFFmpegProcessor:
    @pytest.fixture(name='processor')
    def ffmpeg_processor(self):
        return madam.audio.FFmpegProcessor()

    def test_cannot_resize_audio(self, processor, audio_asset):
        resize_operator = processor.resize(width=12, height=34)

        with pytest.raises(OperatorError):
            resize_operator(audio_asset)

    def test_converted_essence_is_of_specified_type(self, processor, audio_asset):
        conversion_operator = processor.convert(mime_type='audio/mpeg')

        converted_asset = conversion_operator(audio_asset)

        command = 'ffprobe -print_format json -loglevel error -show_format -i pipe:'.split()
        result = subprocess_run(command, input=converted_asset.essence.read(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        video_info = json.loads(result.stdout.decode('utf-8'))
        assert video_info.get('format', {}).get('format_name') == 'mp3'

    def test_converted_essence_stream_has_specified_codec(self, processor, audio_asset):
        conversion_operator = processor.convert(mime_type='audio/mpeg', audio=dict(codec='mp3'))

        converted_asset = conversion_operator(audio_asset)

        command = 'ffprobe -print_format json -loglevel error -show_streams -i pipe:'.split()
        result = subprocess_run(command, input=converted_asset.essence.read(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        video_info = json.loads(result.stdout.decode('utf-8'))
        assert video_info.get('streams', [{}])[0].get('codec_name') == 'mp3'


class TestFFmpegMetadataProcessor:
    @pytest.fixture(name='processor')
    def ffmpeg_metadata_processor(self):
        return madam.audio.FFmpegMetadataProcessor()

    def test_supports_ffmetadata(self, processor):
        assert 'ffmetadata' in processor.formats

    def test_read_returns_correct_metadata_dict_for_mp3_with_id3(self, processor):
        with open('tests/resources/64kbits_with_id3v2-4.mp3', 'rb') as file:
            metadata = processor.read(file)

        assert metadata['ffmetadata']['artist'] == 'Frédéric Chopin'
        assert len(metadata) == 1

    def test_read_returns_correct_metadata_dict_for_opus_with_comments(self, processor):
        with open('tests/resources/sine-440hz-audio-with-comments.opus', 'rb') as file:
            metadata = processor.read(file)

        assert metadata['ffmetadata']['artist'] == 'Frédéric Chopin'
        assert len(metadata) == 1

    def test_read_raises_error_when_file_format_is_unsupported(self, processor, unknown_asset):
        junk_data = unknown_asset.essence

        with pytest.raises(UnsupportedFormatError):
            processor.read(junk_data)

    def test_read_returns_empty_dict_when_mp3_contains_no_metadata(self, processor, mp3_asset):
        data_without_id3 = mp3_asset.essence

        metadata = processor.read(data_without_id3)

        assert not metadata

    def test_strip_returns_essence_without_metadata(self, processor):
        with open('tests/resources/64kbits_with_id3v2-4.mp3', 'rb') as file:
            essence = file.read()
            file.seek(0)
            stripped_essence = processor.strip(file).read()

        assert essence != stripped_essence

    def test_strip_raises_error_when_file_format_is_unsupported_by_ffmpeg(self, processor, unknown_asset):
        junk_data = unknown_asset.essence

        with pytest.raises(UnsupportedFormatError):
            processor.strip(junk_data)

    def test_strip_raises_error_when_file_format_is_unsupported_by_metadata_processor(self, processor, nut_audio_asset):
        essence = nut_audio_asset.essence

        with pytest.raises(UnsupportedFormatError):
            processor.strip(essence)

    def test_combine_returns_mp3_with_metadata(self, processor, mp3_asset, tmpdir):
        essence = mp3_asset.essence
        metadata = dict(ffmetadata=dict(artist='Frédéric Chopin'))

        essence_with_metadata = processor.combine(essence, metadata)

        essence_file = tmpdir.join('essence_with_metadata')
        essence_file.write(essence_with_metadata.read(), 'wb')
        mp3 = EasyMP3(str(essence_file))
        for key, actual in metadata['ffmetadata'].items():
            expected = mp3.tags.get(key)
            if isinstance(expected, list):
                assert actual in expected
            else:
                assert mp3.tags[key] == actual

    def test_combine_returns_opus_with_metadata(self, processor, opus_asset, tmpdir):
        essence = opus_asset.essence
        metadata = dict(ffmetadata=dict(artist='Frédéric Chopin'))

        essence_with_metadata = processor.combine(essence, metadata)

        essence_file = tmpdir.join('essence_with_metadata')
        essence_file.write(essence_with_metadata.read(), 'wb')
        ogg = OggOpus(str(essence_file))
        for key, actual in metadata['ffmetadata'].items():
            expected = ogg.tags.get(key)
            if isinstance(expected, list):
                assert actual in expected
            else:
                assert ogg.tags[key] == actual

    def test_combine_raises_error_when_no_ffmetadata_dict_is_given(self, processor, mp3_asset):
        metadata = {}

        with pytest.raises(ValueError):
            processor.combine(mp3_asset.essence, metadata)

    def test_combine_does_not_modify_essence_without_metadata(self, processor, mp3_asset):
        essence = mp3_asset.essence
        metadata = dict(ffmetadata={})

        essence_with_metadata = processor.combine(essence, metadata)

        assert essence_with_metadata.read() == essence.read()

    def test_combine_raises_error_when_essence_format_is_unsupported_by_ffmeg(self, processor, unknown_asset):
        junk_data = unknown_asset.essence
        metadata = dict(ffmetadata=dict(artist='Frédéric Chopin'))

        with pytest.raises(UnsupportedFormatError):
            processor.combine(junk_data, metadata)

    def test_combine_raises_error_when_file_format_is_unsupported_by_metadata_processor(self, processor, nut_audio_asset):
        essence = nut_audio_asset.essence
        metadata = dict(ffmetadata=dict(artist='Frédéric Chopin'))

        with pytest.raises(UnsupportedFormatError):
            processor.combine(essence, metadata)

    def test_combine_raises_error_when_metadata_format_is_unsupported(self, processor, mp3_asset):
        ffmetadata = {'123abc': 'Test artist'}

        with pytest.raises(UnsupportedFormatError):
            processor.combine(mp3_asset.essence, ffmetadata)

    def test_combine_raises_error_when_metadata_contains_unsupported_keys(self, processor, mp3_asset):
        metadata = dict(ffmetadata=dict(foo='bar'))

        with pytest.raises(ValueError):
            processor.combine(mp3_asset.essence, metadata)
