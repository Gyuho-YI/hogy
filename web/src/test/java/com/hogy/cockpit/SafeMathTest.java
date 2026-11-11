package com.hogy.cockpit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import org.junit.jupiter.api.Test;

import com.hogy.cockpit.util.SafeMath;

class SafeMathTest {

    @Test
    void 분모가_0이거나_없으면_계산불가() {
        assertThat(SafeMath.growth(10.0, 0.0).rate()).isNull();
        assertThat(SafeMath.growth(10.0, null).label()).isEqualTo("계산불가");
        assertThat(SafeMath.ratio(1.0, 0.0)).isNull();
        assertThat(SafeMath.ratio(1.0, -2.0)).isNull();
    }

    @Test
    void 전기_손실이면_절댓값으로_나누고_라벨_부여() {
        assertThat(SafeMath.growth(10.0, -20.0).label()).isEqualTo("흑자전환");
        assertThat(SafeMath.growth(10.0, -20.0).rate()).isCloseTo(1.5, within(1e-9));
        assertThat(SafeMath.growth(-5.0, -20.0).label()).isEqualTo("적자축소");
        assertThat(SafeMath.growth(-30.0, -20.0).label()).isEqualTo("적자확대");
    }

    @Test
    void 역성장은_음수_그대로() {
        assertThat(SafeMath.growth(80.0, 100.0).rate()).isCloseTo(-0.2, within(1e-9));
        assertThat(SafeMath.growth(80.0, 100.0).label()).isEqualTo("정상");
        assertThat(SafeMath.growth(-220.0, 360.0).label()).isEqualTo("적자전환");
    }
}
