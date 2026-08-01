declare module "sm-crypto" {
  export const sm2: {
    doEncrypt(plaintext: string, publicKey: string, cipherMode?: 0 | 1): string;
    doDecrypt(ciphertext: string, privateKey: string, cipherMode?: 0 | 1): string;
    generateKeyPairHex(): { privateKey: string; publicKey: string };
  };
  export const sm3: {
    (input: string): string;
  };
  export const sm4: {
    encrypt(data: string, key: string, options?: { mode?: string; iv?: string }): string;
    decrypt(data: string, key: string, options?: { mode?: string; iv?: string }): string;
  };
}
