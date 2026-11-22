#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <limits.h>
#include <stdbit.h>

#define NUM_START_PRIMES 9
#define CHUNK_SIZE 250000
int initial_primes[NUM_START_PRIMES] = {2, 3, 5, 7, 11, 13, 17, 19, 23};

unsigned long gcd(unsigned long a, unsigned long b){
    unsigned long q = a / b;
    unsigned long r = a % b;
    if (r == 0){
        return b;
    }
    return gcd(b, r);
}

unsigned long lcm(unsigned long a, unsigned long b){
    return (a * b) / gcd(a, b);
}

int valid(unsigned long n){
    for (int i = 0; i < NUM_START_PRIMES; i++){
        if (n % initial_primes[i] == 0 && n != initial_primes[i]){
            return 0;
        }
    }
    return 1;
}

int* get_cycle(int* cycle_size){
    int num = 0;
    unsigned long max = initial_primes[NUM_START_PRIMES - 1];
    for (int i = 0; i < NUM_START_PRIMES; i++){
        max = lcm(max, initial_primes[i]);
    }
    for (unsigned long i = 1; i < max; i += 2){
        if (valid(i)){
            num++;
        }
    }
    *cycle_size = num;
    int* cycle = (int*)malloc(num * sizeof(int));
    int counter = 0;
    unsigned long prev = 1;
    for (unsigned long i = 3; i < max; i += 2){
        if (valid(i)){
            cycle[counter] = i - prev;
            prev = i;
            counter++;
        }
    }
    cycle[num - 1] = max + 1 - prev;
    return cycle;
}

int is_prime(int cycle_length, int* cycle, unsigned long n){
//     for (int i = 0; i < NUM_START_PRIMES; i++){
//         if (n % initial_primes[i] == 0){
//             return 0;
//         }
//     }
    int inc_index = 1;
    unsigned long div = 1 + cycle[0];
    while (div <= n / div){
        if (n % div == 0){
            return 0;
        }
        div +=cycle[inc_index];
        inc_index = (inc_index + 1) % cycle_length;
    }
    return 1;
}

void save_chunk(unsigned long* chunk, unsigned long current_prime, int chunk_id){
    printf("Num Primes: %d\n", CHUNK_SIZE * chunk_id);
    unsigned int gap;
    unsigned int bit_length, enc_length, enc;
    unsigned int bit_count = 0;
    unsigned int val = 0;
    unsigned int byte;
    char* filename = (char*)malloc(50 * sizeof(char));
    sprintf(filename, "database/%d", chunk_id);
    FILE* fptr = fopen(filename, "wb");
    int counter = 0;
    for (int i = 1; i < CHUNK_SIZE; i++){
        gap = (chunk[i] - chunk[i - 1]) / 2;
        if (gap == 0){
            gap = 1;
        }
        bit_length = stdc_bit_width(gap);
        enc_length = 2 * bit_length - 1;
        enc = gap;
        val = (val << enc_length) | enc;
        bit_count += enc_length;
        while (bit_count >= 8){
            byte = (val >> (bit_count - 8)) & 255;
            fwrite(&byte, 1, 1, fptr);
            val = val & ((1 << (bit_count - 8)) - 1);
            bit_count -= 8;
            counter++;
        }
    }
    gap = (current_prime - chunk[CHUNK_SIZE - 1]) / 2;
    bit_length = stdc_bit_width(gap);
    enc_length = 2 * bit_length - 1;
    enc = gap;
    val = (val << enc_length) | enc;
    bit_count += enc_length;
    val = val << (8 - (bit_count % 8));
    bit_count += 8 - (bit_count % 8);
    while (bit_count > 0){
        byte = (val >> (bit_count - 8)) & 255;
        fwrite(&byte, 1, 1, fptr);
        val = val & ((1 << (bit_count - 8)) - 1);
        bit_count -= 8;
        counter++;
    }
    fclose(fptr);
}

int main(int argc, char** argv){
    int cycle_length = 0;
    int* cycle = get_cycle(&cycle_length);
    printf("Cycle Length: %d\n", cycle_length);

    unsigned long num_primes = 0;
    unsigned long* chunk = (unsigned long*)malloc(CHUNK_SIZE * sizeof(unsigned long));
    for (int i = 0; i < NUM_START_PRIMES; i++){
        chunk[i] = initial_primes[i];
        num_primes++;
    }
    unsigned long next_check = 1 + cycle[0];
    unsigned long cycle_index = 1;
    int is_p;
    while (1){
        is_p = is_prime(cycle_length, cycle, next_check);
        if (is_p){
            if (num_primes % CHUNK_SIZE == 0){
                save_chunk(chunk, next_check, num_primes / CHUNK_SIZE);
            }
            chunk[num_primes % CHUNK_SIZE] = next_check;
            num_primes++;
        }
        next_check += cycle[cycle_index];
        cycle_index = (cycle_index + 1) % cycle_length;
    }
}