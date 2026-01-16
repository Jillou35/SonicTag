
import numpy as np

class FEC:
    """
    Forward Error Correction and Integrity module for DeepSeal.
    Implements:
    - CRC-8 for integrity check.
    - Hamming(7,4) for error correction (1 bit correction per nibble).
    """

    def __init__(self):
        # Hamming(7,4) Matrices
        # Generator Matrix G (4x7)
        self.G = np.array([
            [1, 1, 0, 1, 0, 0, 0],
            [0, 1, 1, 0, 1, 0, 0],
            [1, 1, 1, 0, 0, 1, 0],
            [1, 0, 1, 0, 0, 0, 1]
        ], dtype=int)

        # Parity Check Matrix H (3x7)
        self.H = np.array([
            [1, 0, 0, 1, 0, 1, 1],
            [0, 1, 0, 1, 1, 1, 0],
            [0, 0, 1, 0, 1, 1, 1]
        ], dtype=int)
        
        # Syndrome to Error Position map (Binary value of column in H indicates position + 1)
        # Columns of H:
        # 1: [1,0,0] -> 1 (Pos 0) check: this is standard hamming.
        # Actually, let's derive the map dynamically or use fixed.
        # Syndrome [s0, s1, s2]. 
        # Error Map: (s2*4 + s1*2 + s0) -> Index
        # Let's verify standard H form.
        # The above H corresponds to:
        # p1 = d1 + d2 + d4
        # p2 = d1 + d3 + d4
        # p3 = d2 + d3 + d4 
        # ... standard Hamming setup.
        
    def crc8(self, data_bytes: bytes) -> int:
        """
        Calculate CRC-8 (Polynomial 0x07)
        """
        crc = 0
        for b in data_bytes:
            crc ^= b
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x07
                else:
                    crc <<= 1
                crc &= 0xFF
        return crc

    def encode_hamming(self, bits: np.ndarray) -> np.ndarray:
        """
        Encode bits using Hamming(7,4). 
        Input length must be multiple of 4.
        """
        if len(bits) % 4 != 0:
            raise ValueError("Input bits length must be multiple of 4")
        
        n_nibbles = len(bits) // 4
        encoded = []
        
        for i in range(n_nibbles):
            nibble = bits[i*4 : (i+1)*4]
            # Codeword = Nibble * G
            codeword = np.dot(nibble, self.G) % 2
            encoded.append(codeword)
            
        return np.concatenate(encoded)

    def decode_hamming(self, bits: np.ndarray) -> np.ndarray:
        """
        Decode bits using Hamming(7,4).
        Corrects 1 error per 7-bit block.
        Input length must be multiple of 7.
        """
        if len(bits) % 7 != 0:
            raise ValueError("Input bits length must be multiple of 7")
        
        n_blocks = len(bits) // 7
        decoded = []
        
        # Syndrome map: integer value of syndrome vector -> bit index to flip
        # Based on H definition above:
        # col 0: [1,0,0] -> val 1. Error at idx 0
        # col 1: [0,1,0] -> val 2. Error at idx 1
        # col 2: [0,0,1] -> val 4. Error at idx 2
        # col 3: [1,1,0] -> val 3. Error at idx 3
        # col 4: [0,1,1] -> val 6. Error at idx 4
        # col 5: [1,1,1] -> val 7. Error at idx 5
        # col 6: [1,0,1] -> val 5. Error at idx 6
        
        syndrome_to_idx = {
            1: 0, 2: 1, 4: 2, 3: 3, 6: 4, 7: 5, 5: 6
        }
        
        for i in range(n_blocks):
            block = bits[i*7 : (i+1)*7].copy()
            
            # Calculate Syndrome: H * r^T
            syndrome_vec = np.dot(self.H, block) % 2
            syndrome_val = syndrome_vec[0]*1 + syndrome_vec[1]*2 + syndrome_vec[2]*4
            
            if syndrome_val > 0:
                # Error detected
                if syndrome_val in syndrome_to_idx:
                    err_idx = syndrome_to_idx[syndrome_val]
                    # Flip bit
                    block[err_idx] = 1 - block[err_idx]
            
            # Extract data bits (first 4 bits in our G construction are NOT systematic like that)
            # Wait, my G matrix:
            # Row 0: 1 1 0 1 0 0 0 -> contributes to pos 0,1,3
            # It's not a systematic code generation where data is just copied.
            # Systematic G usually [I | P]. My G above is mixed.
            # Actually, looking at G:
            # Cols 4,5,6 are [0,0,0]... wait. 
            # Col 4: [0,1,0,0]T -> d2
            # Col 5: [0,0,1,0]T -> d3
            # Col 6: [0,0,0,1]T -> d4
            # Col 2: [0,1,1,1]T -> d2+d3+d4? No.
            
            # Let's switch to a Systematic Generator for sanity.
            # G = [I4 | P]
            # I4 (4x4 identity) + P (4x3 parity)
            # data: d1 d2 d3 d4
            # codeword: d1 d2 d3 d4 p1 p2 p3
            
            # Let's assume systematic decoding is easier.
            # Actually, I'll use a fixed Systematic G.
            pass
        
        return np.concatenate(decoded) if decoded else np.array([], dtype=int)

class SystematicFEC(FEC):
    def __init__(self):
        # Systematic Hamming(7,4)
        # d1 d2 d3 d4 p1 p2 p3
        # p1 = d1+d2+d4
        # p2 = d1+d3+d4
        # p3 = d2+d3+d4
        
        self.G = np.array([
            [1, 0, 0, 0, 1, 1, 0],
            [0, 1, 0, 0, 1, 0, 1],
            [0, 0, 1, 0, 0, 1, 1],
            [0, 0, 0, 1, 1, 1, 1]
        ], dtype=int)
        
        # H = [P^T | I3]
        self.H = np.array([
            [1, 1, 0, 1, 1, 0, 0],
            [1, 0, 1, 1, 0, 1, 0],
            [0, 1, 1, 1, 0, 0, 1]
        ], dtype=int)
        
    def decode_hamming(self, bits: np.ndarray) -> np.ndarray:
        if len(bits) % 7 != 0: raise ValueError("Len must be multiple of 7")
        n_blocks = len(bits) // 7
        decoded = []
        
        # Syndrome map for H defined above
        # H cols:
        # 0: 110 (3) -> bit 0
        # 1: 101 (5) -> bit 1
        # 2: 011 (6) -> bit 2
        # 3: 111 (7) -> bit 3
        # 4: 100 (1) -> bit 4 (p1)
        # 5: 010 (2) -> bit 5 (p2)
        # 6: 001 (4) -> bit 6 (p3)
        # s = [s0, s1, s2] -> val = s0 + s1*2 + s2*4
        
        syndrome_map = {
            3: 0, 5: 1, 6: 2, 7: 3, # Data bits
            1: 4, 2: 5, 4: 6        # Parity bits
        }
        
        for i in range(n_blocks):
            block = bits[i*7 : (i+1)*7].copy()
            syndrome_vec = np.dot(self.H, block) % 2
            val = syndrome_vec[0] + syndrome_vec[1]*2 + syndrome_vec[2]*4
            
            if val > 0:
                if val in syndrome_map:
                    idx = syndrome_map[val]
                    block[idx] = 1 - block[idx] # Correct
            
            # Systematic: Data is first 4 bits
            decoded.append(block[:4])
            
        return np.concatenate(decoded)
