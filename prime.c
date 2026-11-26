#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <limits.h>
#include <stdbit.h>
#include <unistd.h>
#include <pthread.h>

#define NUM_START_PRIMES 8
#define CHUNK_SIZE 250000
int initial_primes[NUM_START_PRIMES] = {2, 3, 5, 7, 11, 13, 17, 19};
#define NUM_KNOWN_PRIMES 1000000
unsigned long known_primes[NUM_KNOWN_PRIMES];


struct Prime_Block {
    char* block;
    unsigned long start;
};

struct Args {
    struct Prime_Block* block;
    int* cycle;
    int cycle_length;
};

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
        if (n % initial_primes[i] == 0){
            return 0;
        }
    }
    return 1;
}

int* get_cycle(int* cycle_size, int* wheel_length){
    int num = 0;
    unsigned long max = initial_primes[NUM_START_PRIMES - 1];
    for (int i = 0; i < NUM_START_PRIMES; i++){
        max = lcm(max, initial_primes[i]);
    }
    *wheel_length = max;
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
    for (int i = 0; i < NUM_START_PRIMES; i++){
        if (n % initial_primes[i] == 0){
            return 0;
        }
    }
    unsigned long prime;
    for (int i = 0; i < NUM_KNOWN_PRIMES; i++){
        prime = known_primes[i];
        if (prime * prime > n){
            return 1;
        } else if (n % prime == 0){
            return 0;
        }
    }
//    int inc_index = 1;
//    unsigned long div = 1 + cycle[0];
//    while (div * div <= n){
//        if (n % div == 0){
//            return 0;
//        }
//        div += cycle[inc_index];
//        inc_index = (inc_index + 1) % cycle_length;
//    }
//    printf("Num: %lu  Count: %ld\n", n, count);
    return 1;
}

int is_naive_prime(int cycle_length, int* cycle, unsigned long n){
    for (int i = 0; i < NUM_START_PRIMES; i++){
        if (n % initial_primes[i] == 0){
            return 0;
        }
    }
    int inc_index = 1;
    unsigned long div = 1 + cycle[0];
    while (div * div <= n){
        if (n % div == 0){
            return 0;
        }
        div += cycle[inc_index];
        inc_index = (inc_index + 1) % cycle_length;
    }
//    printf("Num: %lu  Count: %ld\n", n, count);
    return 1;
}

void calculate_known_primes(int* cycle, int cycle_length){
    for (int i = 0; i < NUM_START_PRIMES; i++){
        known_primes[i] = initial_primes[i];
    }
    int index = NUM_START_PRIMES;
    int inc_index = 1;
    unsigned long n = 1 + cycle[0];
    while (index < NUM_KNOWN_PRIMES){
        if (is_naive_prime(cycle_length, cycle, n)){
            known_primes[index] = n;
            index++;
        }
        n += cycle[inc_index];
        inc_index = (inc_index + 1) % cycle_length;
    }
}

void* calculate_block(void* args){
    struct Prime_Block* block = ((struct Args*)args)->block;
    int* cycle = ((struct Args*)args)->cycle;
    int cycle_length = ((struct Args*)args)->cycle_length;
    unsigned long n = block->start;
    for (int i = 0; i < cycle_length; i++){
        if (is_prime(cycle_length, cycle, n) && n != 1){
            block->block[i] = 1;
        } else {
            block->block[i] = 0;
        }
        n += cycle[i];
    }
    return NULL;
}

void save_chunk(unsigned long* chunk, unsigned long current_prime, int chunk_id){
    unsigned int gap;
    unsigned int bit_length, enc_length, enc;
    unsigned int bit_count = 0;
    unsigned int val = 0;
    unsigned int byte;
    char* filename = (char*)malloc(50 * sizeof(char));
    sprintf(filename, "database/%d", chunk_id);
    FILE* fptr = fopen(filename, "wb");
    printf("Writing to %s\n", filename);
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

void generate_primes(unsigned long start, unsigned long** prime_chunk, int* chunk_index, int* num_chunks, unsigned long* full_wheel, int* cycle, int cycle_length, int wheel_length){
    if (*num_chunks == 1){
        for (int i = 0; i < NUM_START_PRIMES; i++){
            (*prime_chunk)[i] = initial_primes[i];
        }
        *chunk_index = NUM_START_PRIMES;
    }
    long num_threads = sysconf(_SC_NPROCESSORS_ONLN);
//    long num_threads = 1;
    pthread_t* threads = (pthread_t*)malloc(num_threads * sizeof(pthread_t));
    struct Prime_Block** blocks = (struct Prime_Block**)malloc(num_threads * sizeof(struct Prime_Block*));
    struct Args** args = (struct Args**)malloc(num_threads * sizeof(struct Args));
    struct Prime_Block** blocks2 = (struct Prime_Block**)malloc(num_threads * sizeof(struct Prime_Block*));
    struct Args** args2 = (struct Args**)malloc(num_threads * sizeof(struct Args));
    for (int i = 0; i < num_threads; i++){
        blocks[i] = (struct Prime_Block*)malloc(sizeof(struct Prime_Block));
        blocks[i]->block = (char*)malloc(cycle_length * sizeof(char));
        blocks2[i] = (struct Prime_Block*)malloc(sizeof(struct Prime_Block));
        blocks2[i]->block = (char*)malloc(cycle_length * sizeof(char));
        args[i] = (struct Args*)malloc(sizeof(struct Args));
        args[i]->block = blocks[i];
        args[i]->cycle = cycle;
        args[i]->cycle_length = cycle_length;
        args2[i] = (struct Args*)malloc(sizeof(struct Args));
        args2[i]->block = blocks2[i];
        args2[i]->cycle = cycle;
        args2[i]->cycle_length = cycle_length;
    }
    unsigned long next_check = start;
    for (int i = 0; i < num_threads; i++){
        blocks[i]->start = next_check;
        next_check += wheel_length;
        pthread_create(&threads[i], NULL, calculate_block, args[i]);
    }
    int first = 1;
    while (1){
        if (!first){
            for (int i = 0; i < num_threads; i++){
                for (int j = 0; j < cycle_length; j++){
                    if (blocks2[i]->block[j]){
                        if (*chunk_index == 0){
                            save_chunk(*prime_chunk, blocks2[i]->start + full_wheel[j], *num_chunks);
                            *num_chunks += 1;
                        }
                        (*prime_chunk)[*chunk_index] = blocks2[i]->start + full_wheel[j];
                        *chunk_index = (*chunk_index + 1) % CHUNK_SIZE;
                    }
                }
            }
        }
        for (int i = 0; i < num_threads; i++){
            pthread_join(threads[i], NULL);
            blocks2[i]->start = next_check;
            next_check += wheel_length;
            pthread_create(&threads[i], NULL, calculate_block, args2[i]);
        }
        for (int i = 0; i < num_threads; i++){
            for (int j = 0; j < cycle_length; j++){
                if (blocks[i]->block[j]){
                    if (*chunk_index == 0){
                        save_chunk(*prime_chunk, blocks[i]->start + full_wheel[j], *num_chunks);
                        *num_chunks += 1;
                    }
                    (*prime_chunk)[*chunk_index] = blocks[i]->start + full_wheel[j];
                    *chunk_index = (*chunk_index + 1) % CHUNK_SIZE;
                }
            }
        }
        for (int i = 0; i < num_threads; i++){
            pthread_join(threads[i], NULL);
            blocks[i]->start = next_check;
            next_check += wheel_length;
            pthread_create(&threads[i], NULL, calculate_block, args[i]);
        }
        first = 0;
    }
}

unsigned long calculate_partial_wheel(unsigned long start, unsigned long** prime_chunk, int* chunk_index, int* num_chunks, unsigned long* full_wheel, int* cycle, int cycle_length, int wheel_length){
    unsigned long mod = (start % wheel_length) - 1;
    int mod_index = 0;
    for (int i = 0; i < cycle_length; i++){
        if (full_wheel[i] == mod){
            mod_index = i;
            break;
        }
    }
    int first = 1;
    while (mod_index != 0){
        if (is_prime(cycle_length, cycle, start)){
            if (*chunk_index == 0 && !first){
                save_chunk(*prime_chunk, start, *num_chunks);
                *num_chunks += 1;
            }
            (*prime_chunk)[*chunk_index] = start;
            *chunk_index = (*chunk_index + 1) % CHUNK_SIZE;
        }
        start += cycle[mod_index];
        mod_index = (mod_index + 1) % cycle_length;
        first = 0;
    }
    return start;
}

int main(int argc, char** argv){
    int cycle_length = 0;
    int wheel_length = 0;
    int* cycle = get_cycle(&cycle_length, &wheel_length);

    calculate_known_primes(cycle, cycle_length);

    printf("Checking %f percent of all numbers\n", 100 * (float)cycle_length / wheel_length);
    unsigned long* full_wheel = (unsigned long*)malloc(cycle_length * sizeof(unsigned long));
    full_wheel[0] = 0;
    for (int i = 1; i < cycle_length; i++){
        full_wheel[i] = full_wheel[i - 1] + cycle[i - 1];
    }

    unsigned long* prime_chunk = (unsigned long*)malloc(CHUNK_SIZE * sizeof(unsigned long));
    int chunk_index = 0;

    unsigned long start = 1;
    int num_chunks = 1;
    if (argc > 1){
        start = strtol(argv[1], NULL, 10);
        num_chunks = (int)(strtol(argv[2], NULL, 10));
        printf("Old Start: %ld\n", start);
        start = calculate_partial_wheel(start, &prime_chunk, &chunk_index, &num_chunks, full_wheel, cycle, cycle_length, wheel_length);
        printf("New Start: %ld\n", start);
    }

    generate_primes(start, &prime_chunk, &chunk_index, &num_chunks, full_wheel, cycle, cycle_length, wheel_length);

}