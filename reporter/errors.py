"""프로그램에서 쓰는 오류 종류."""


class ConfigError(Exception):
    """설정 파일(YAML)이 잘못됐을 때."""


class KakaoAuthError(Exception):
    """카카오 토큰이 없거나 만료돼서 다시 인증이 필요할 때."""


class DeliveryError(Exception):
    """발송(이메일·카카오 등)에 실패했을 때."""
