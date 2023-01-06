import numpy as np

def _twos_comp(val, bits):
    """compute the 2's complement of int value val"""
    if (val & (1 << (bits - 1))) != 0:
        val = val - (1 << bits)
    return int(val)

class Model:
    def __init__(self, IN_DW, OUT_DW, PSS_LEN, PSS_LOCAL, ALGO, TRUNCATE_INPUTS=True):
        self.PSS_LEN = int(PSS_LEN)
        self.OUT_DW = int(OUT_DW)
        self.IN_DW = int(IN_DW)
        self.TRUNCATE_INPUTS = int(TRUNCATE_INPUTS)
        self.TAP_DW = 32
        self.POSSIBLE_IN_DW = int(self.OUT_DW \
                        - (np.ceil(np.log2(self.PSS_LEN)+1)) * 2  - 3)
        self.IN_OP_DW = self.POSSIBLE_IN_DW//2
        self.TAP_OP_DW = self.POSSIBLE_IN_DW//2 + self.POSSIBLE_IN_DW%2
        if self.TRUNCATE_INPUTS:
            self.trunc_taps = self.TAP_DW//2 - self.TAP_OP_DW
            self.trunc_in = self.IN_DW//2 - self.IN_OP_DW
        else:
            self.trunc_taps = 0
            self.trunc_in = 0

        # print(f'model IN_DW = {IN_DW}')
        # print(f'model OUT_DW = {OUT_DW}')
        # print(f'model PSS_LEN = {PSS_LEN}')
        # print(f'model PSS_LOCAL = {PSS_LOCAL}')
        self.taps = np.empty(PSS_LEN, 'complex')

        if False:
            # don't do rounding for truncations, because its also not implemented in HDL
            if self.trunc_taps > 1:
                round_bits = 2 ** (self.trunc_taps - 2) - 1
            else:
                round_bits = 0
        else:
            round_bits = 0

        for i in range(PSS_LEN):
            self.taps[i] =   ((_twos_comp(((PSS_LOCAL>>(32*i)) & 0xFFFF), 16) + round_bits) >> self.trunc_taps) \
                           + 1j*((_twos_comp(((PSS_LOCAL>>(32*i+16)) & 0xFFFF), 16) + round_bits) >> self.trunc_taps)
    
        # for i in range(PSS_LEN):
        #     print(f'taps[{i}] = {self.taps[i]}')

        self.reset()

    def tick(self):
        self.in_pipeline[1:] = self.in_pipeline[:-1]
        self.valid[1:] = self.valid[:-1]
        self.valid[0] = False
        
        if self.in_buffer is not None:
            self.in_pipeline[0] = self.in_buffer
            self.valid[0] = True
            self.in_buffer = None

    def set_data(self, data_in):
        self.in_buffer = (_twos_comp((data_in & 0xFFFF), self.IN_DW//2) >> self.trunc_in) \
                         + 1j*(_twos_comp(((data_in>>(self.IN_DW//2)) & 0xFFFF), self.IN_DW//2) >> self.trunc_in)

    def reset(self):
        self.in_pipeline = np.zeros(self.PSS_LEN, 'complex')
        self.in_buffer = None
        self.valid = np.zeros(1, bool)
    
    def data_valid(self):
        return self.valid[-1]

    def get_data(self):
        result_re = 0
        result_im = 0
        for i in range(self.PSS_LEN):
            # bit growth inside this loop is ceil(log2(PSS_LEN)) + IN_DW/2 for result_re and result_im
            result_re += (  int(self.taps[i].real) * int(self.in_pipeline[self.PSS_LEN - i - 1].real) \
                            + int(self.taps[i].imag) * int(self.in_pipeline[self.PSS_LEN - i - 1].imag))
            result_im += (  int(self.taps[i].real) * int(self.in_pipeline[self.PSS_LEN - i - 1].imag) \
                            - int(self.taps[i].imag) * int(self.in_pipeline[self.PSS_LEN - i - 1].real))
        # bit growth self.IN_DW/2 + 1
        result_abs = result_re ** 2 + result_im ** 2
        # output is unsigned, therefore needs 1 bit less
        if self.TRUNCATE_INPUTS:
            return result_abs & (2 ** self.OUT_DW - 1)
        else:
            return (result_abs >> int(np.ceil(np.log2(self.PSS_LEN)) - 1 + self.IN_DW)) & (2 ** self.OUT_DW - 1)
