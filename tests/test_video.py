import json
import subprocess

import pytest

import madam.video
from madam.core import OperatorError, UnsupportedFormatError
from madam.future import subprocess_run
from assets import image_asset, jpeg_asset, png_asset, gif_asset
from assets import video_asset, mp4_asset, y4m_asset
from assets import unknown_asset


class TestFFmpegProcessor:
    @pytest.fixture(name='processor', scope='class')
    def ffmpeg_processor(self):
        return madam.video.FFmpegProcessor()

    def test_resize_raises_error_for_invalid_dimensions(self, processor, video_asset):
        resize = processor.resize(width=12, height=-34)

        with pytest.raises(ValueError):
            resize(video_asset)

    def test_resize_returns_asset_with_correct_dimensions(self, processor, video_asset):
        resize = processor.resize(width=12, height=34)

        resized_asset = resize(video_asset)

        assert resized_asset.width == 12
        assert resized_asset.height == 34

    def test_resize_returns_essence_with_same_format(self, processor, y4m_asset):
        resize = processor.resize(width=12, height=34)

        resized_asset = resize(y4m_asset)

        command = 'ffprobe -print_format json -loglevel error -show_format -i pipe:'.split()
        result = subprocess_run(command, input=resized_asset.essence.read(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        video_info = json.loads(result.stdout.decode('utf-8'))
        assert video_info.get('format', {}).get('format_name') == 'yuv4mpegpipe'

    def test_resize_returns_essence_with_correct_dimensions(self, processor, video_asset):
        resize_operator = processor.resize(width=12, height=34)

        resized_asset = resize_operator(video_asset)

        command = 'ffprobe -print_format json -loglevel error -show_streams -i pipe:'.split()
        result = subprocess_run(command, input=resized_asset.essence.read(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        video_info = json.loads(result.stdout.decode('utf-8'))
        first_stream = video_info.get('streams', [{}])[0]
        assert first_stream.get('width') == 12
        assert first_stream.get('height') == 34

    def test_resize_raises_error_for_unknown_formats(self, processor, unknown_asset):
        resize_operator = processor.resize(width=12, height=34)

        with pytest.raises(UnsupportedFormatError):
            resize_operator(unknown_asset)

    @pytest.fixture(scope='class')
    def converted_asset(self, processor, video_asset):
        conversion_operator = processor.convert(mime_type='video/x-matroska',
                                                video=dict(codec='vp9'),
                                                audio=dict(codec='opus'))
        converted_asset = conversion_operator(video_asset)
        return converted_asset

    def test_converted_asset_receives_correct_mime_type(self, converted_asset):
        assert converted_asset.mime_type == 'video/x-matroska'

    def test_convert_creates_new_asset(self, processor, video_asset):
        conversion_operator = processor.convert(mime_type='video/x-matroska')

        converted_asset = conversion_operator(video_asset)

        assert isinstance(converted_asset, madam.core.Asset)
        assert converted_asset != video_asset

    def test_convert_raises_error_when_it_fails(self, processor, unknown_asset):
        conversion_operator = processor.convert(mime_type='video/x-matroska')

        with pytest.raises(OperatorError):
            conversion_operator(unknown_asset)

    def test_converted_essence_is_of_specified_type(self, converted_asset):
        command = 'ffprobe -print_format json -loglevel error -show_format -i pipe:'.split()
        result = subprocess_run(command, input=converted_asset.essence.read(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        video_info = json.loads(result.stdout.decode('utf-8'))
        assert video_info.get('format', {}).get('format_name') == 'matroska,webm'

    def test_converted_essence_stream_has_specified_codec(self, converted_asset):
        command = 'ffprobe -print_format json -loglevel error -show_streams -i pipe:'.split()
        result = subprocess_run(command, input=converted_asset.essence.read(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        video_info = json.loads(result.stdout.decode('utf-8'))
        assert video_info.get('streams', [{}])[0].get('codec_name') == 'vp9'

    def test_extract_frame_asset_receives_correct_mime_type(self, processor, video_asset, image_asset):
        image_mime_type = image_asset.mime_type
        extract_frame_operator = processor.extract_frame(mime_type=image_mime_type)

        extracted_asset = extract_frame_operator(video_asset)

        assert extracted_asset.mime_type == image_mime_type

    def test_extract_frame_raises_error_for_unknown_source_format(self, processor, unknown_asset, image_asset):
        image_mime_type = image_asset.mime_type
        extract_frame_operator = processor.extract_frame(mime_type=image_mime_type)

        with pytest.raises(UnsupportedFormatError):
            extract_frame_operator(unknown_asset)

    def test_extract_frame_raises_error_for_unknown_target_format(self, processor, video_asset):
        image_mime_type = 'application/x-unknown'
        extract_frame_operator = processor.extract_frame(mime_type=image_mime_type)

        with pytest.raises(UnsupportedFormatError):
            extract_frame_operator(video_asset)
