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


struct Sieve_Block {
    char* block;
    unsigned long start;
};

struct Args {
    struct Sieve_Block* block;
    int* cycle;
    int cycle_length;
    int wheel_length;
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
            printf("\r%d/%d", index, NUM_KNOWN_PRIMES);
        }
        n += cycle[inc_index];
        inc_index = (inc_index + 1) % cycle_length;
    }
    printf("\n");
}

void* calculate_block(void* args){
    struct Sieve_Block* block = ((struct Args*)args)->block;
    int* cycle = ((struct Args*)args)->cycle;
    int cycle_length = ((struct Args*)args)->cycle_length;
    int wheel_length = ((struct Args*)args)->wheel_length;
    unsigned long start = block->start;
    unsigned long max = block->start + wheel_length;
    unsigned long n = 0;
    for (int i = 0; i < cycle_length; i++){
        block->block[n] = 1;
        n += cycle[i];
    }
    if (start == 1){
        block->block[0] = 0;
    }
    unsigned long val;
    for (int i = 0; i < NUM_KNOWN_PRIMES; i++){
        n = known_primes[i];
        if (n > max / n){
            return NULL;
        }
        val = (n - (start % n)) % n;
        while (val < wheel_length){
            if (start + val > n){
                block->block[val] = 0;
            }
            val += n;
        }
    }
    return NULL;
}

int index_of(int val, unsigned int* array, int length){
    for (int i = 0; i < length; i++){
        if (array[i] == val){
            return i;
        }
    }
    return -1;
}

void get_common_gaps(unsigned long current_prime, unsigned long* chunk, unsigned int* common_gaps, unsigned int* frequencies, int* length){
    *length = 0;
    for (int i = 0; i < CHUNK_SIZE; i++){
        common_gaps[i] = -1;
    }
    int index;
    for (int i = 1; i < CHUNK_SIZE; i++){
        index = index_of((chunk[i] - chunk[i - 1]) / 2, common_gaps, *length);
        if (index == -1){
            common_gaps[*length] = (chunk[i] - chunk[i - 1]) / 2;
            frequencies[*length] = 0;
            index = *length;
            *length += 1;
        }
        frequencies[index]++;
    }
    index = index_of((current_prime - chunk[CHUNK_SIZE - 1]) / 2, common_gaps, *length);
        if (index == -1){
            common_gaps[*length] = (current_prime - chunk[CHUNK_SIZE - 1]) / 2;
            frequencies[*length] = 0;
            index = *length;
            *length += 1;
        }
        frequencies[index]++;
}

void swap(unsigned int* common_gaps, unsigned int* frequencies, int i, int j){
    unsigned int tmp = common_gaps[i];
    common_gaps[i] = common_gaps[j];
    common_gaps[j] = tmp;
    tmp = frequencies[i];
    frequencies[i] = frequencies[j];
    frequencies[j] = tmp;
}

int median(unsigned int a, unsigned int b, unsigned int c){
    unsigned int tmp;
    if (a > b){
        tmp = a;
        a = b;
        b = tmp;
    } if (b > c){
        tmp = b;
        b = c;
        c = tmp;
    } if (a > b){
        tmp = a;
        a = b;
        b = a;
    }
    return b;
}

void quick_sort(unsigned int* common_gaps, unsigned int* frequencies, int length){
    if (length < 2){
        return;
    } else if (length == 2){
        if (frequencies[0] < frequencies[1]){
            swap(common_gaps, frequencies, 0, 1);
        }
        return;
    }
    int index = length - 1;
    unsigned int pivot = median(frequencies[length / 2], frequencies[length / 2 - 1], frequencies[length / 2 + 1]);
    int i = 0;
    while (index >= 0 && i < index){
        if (frequencies[i] < pivot){
            swap(common_gaps, frequencies, i, index);
            index--;
        } else {
            i++;
        }
    }
    quick_sort(common_gaps, frequencies, index);
    quick_sort(&common_gaps[index], &frequencies[index], length - index);
}

void save_chunk(unsigned long* chunk, unsigned int* common_gaps, unsigned int* frequencies, unsigned long current_prime, int chunk_id){
    unsigned int gap;
    unsigned int bit_length, enc_length, enc;
    unsigned int bit_count = 0;
    unsigned int val = 0;
    unsigned int byte;
    int num_gaps = 0;
    get_common_gaps(current_prime, chunk, &common_gaps[1], &frequencies[1], &num_gaps);
    quick_sort(&common_gaps[1], &frequencies[1], num_gaps);
    common_gaps[0] = num_gaps;
    unsigned int k = 3;
    unsigned int M = 1 << k;
    char* filename = (char*)malloc(50 * sizeof(char));
    sprintf(filename, "database/%d-%lu", chunk_id, current_prime);
    printf("\rWriting to %s . . .", filename);
    FILE* fptr = fopen(filename, "wb");
    fwrite(&k, 1, 1, fptr);
    unsigned int q, r;
    int index;
    for (int i = 0; i < num_gaps + 1; i++){
        q = 1 + common_gaps[i] / M;
        r = common_gaps[i] % M;
        bit_length = stdc_bit_width(q);
        enc_length = 2 * bit_length - 1 + k;
        enc = (q << k) | r;
        val = (val << enc_length) | enc;
        bit_count += enc_length;
        while (bit_count >= 8){
            byte = (val >> (bit_count - 8)) & 255;
            fwrite(&byte, 1, 1, fptr);
            val = val & ((1 << (bit_count - 8)) - 1);
            bit_count -= 8;
        }
    }
    for (int i = 1; i < CHUNK_SIZE; i++){
        index = index_of((chunk[i] - chunk[i - 1]) / 2, &common_gaps[1], num_gaps);
        q = 1 + index / M;
        r = index % M;
        bit_length = stdc_bit_width(q);
        enc_length = 2 * bit_length - 1 + k;
        enc = (q << k) | r;
        val = (val << enc_length) | enc;
        bit_count += enc_length;
        while (bit_count >= 8){
            byte = (val >> (bit_count - 8)) & 255;
            fwrite(&byte, 1, 1, fptr);
            val = val & ((1 << (bit_count - 8)) - 1);
            bit_count -= 8;
        }
    }
    index = index_of((current_prime - chunk[CHUNK_SIZE - 1]) / 2, &common_gaps[1], num_gaps);
    q = 1 + index / M;
    r = index % M;
    bit_length = stdc_bit_width(q);
    enc_length = 2 * bit_length - 1 + k;
    enc = (q << k) | r;
    val = (val << enc_length) | enc;
    bit_count += enc_length;
    val = val << (8 - (bit_count % 8));
    bit_count += 8 - (bit_count % 8);
    while (bit_count > 0){
        byte = (val >> (bit_count - 8)) & 255;
        fwrite(&byte, 1, 1, fptr);
        val = val & ((1 << (bit_count - 8)) - 1);
        bit_count -= 8;
    }
    fclose(fptr);
}

void generate_primes(unsigned long start, unsigned int* common_gaps, unsigned int* frequencies, unsigned long** prime_chunk, int* chunk_index, int* num_chunks, unsigned long* full_wheel, int* cycle, int cycle_length, int wheel_length){
    if (*num_chunks == 1){
        for (int i = 0; i < NUM_START_PRIMES; i++){
            (*prime_chunk)[i] = initial_primes[i];
        }
        *chunk_index = NUM_START_PRIMES;
    }

    long num_threads = sysconf(_SC_NPROCESSORS_ONLN);
//    long num_threads = 1;
    pthread_t* threads = (pthread_t*)malloc(num_threads * sizeof(pthread_t));
    struct Sieve_Block** blocks = (struct Sieve_Block**)malloc(num_threads * sizeof(struct Sieve_Block*));
    struct Args** args = (struct Args**)malloc(num_threads * sizeof(struct Args));
    struct Sieve_Block** blocks2 = (struct Sieve_Block**)malloc(num_threads * sizeof(struct Sieve_Block*));
    struct Args** args2 = (struct Args**)malloc(num_threads * sizeof(struct Args));
    for (int i = 0; i < num_threads; i++){
        blocks[i] = (struct Sieve_Block*)malloc(sizeof(struct Sieve_Block));
        blocks[i]->block = (char*)malloc(wheel_length * sizeof(char));
        blocks2[i] = (struct Sieve_Block*)malloc(sizeof(struct Sieve_Block));
        blocks2[i]->block = (char*)malloc(wheel_length * sizeof(char));
        for (int j = 0; j < wheel_length; j++){
            blocks[i]->block[j] = 0;
            blocks2[i]->block[j] = 0;
        }
        args[i] = (struct Args*)malloc(sizeof(struct Args));
        args[i]->block = blocks[i];
        args[i]->cycle = cycle;
        args[i]->cycle_length = cycle_length;
        args[i]->wheel_length = wheel_length;
        args2[i] = (struct Args*)malloc(sizeof(struct Args));
        args2[i]->block = blocks2[i];
        args2[i]->cycle = cycle;
        args2[i]->cycle_length = cycle_length;
        args2[i]->wheel_length = wheel_length;
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
                for (int j = 0; j < wheel_length; j += 2){
                    if (blocks2[i]->block[j]){
                        if (*chunk_index == 0){
                            save_chunk(*prime_chunk, common_gaps, frequencies, blocks2[i]->start + j, *num_chunks);
                            *num_chunks += 1;
                        }
                        (*prime_chunk)[*chunk_index] = blocks2[i]->start + j;
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
            for (int j = 0; j < wheel_length; j++){
                if (blocks[i]->block[j]){
                    if (*chunk_index == 0){
                        save_chunk(*prime_chunk, common_gaps, frequencies, blocks[i]->start + j, *num_chunks);
                        *num_chunks += 1;
                    }
                    (*prime_chunk)[*chunk_index] = blocks[i]->start + j;
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
//    unsigned long mod = (start % wheel_length) - 1;
//    int mod_index = 0;
//    for (int i = 0; i < cycle_length; i++){
//        if (full_wheel[i] == mod){
//            mod_index = i;
//            break;
//        }
//    }
//    int first = 1;
//    while (mod_index != 0){
//        if (is_naive_prime(cycle_length, cycle, start)){
//            if (*chunk_index == 0 && !first){
//                save_chunk(*prime_chunk, start, *num_chunks);
//                *num_chunks += 1;
//            }
//            (*prime_chunk)[*chunk_index] = start;
//            *chunk_index = (*chunk_index + 1) % CHUNK_SIZE;
//        }
//        start += cycle[mod_index];
//        mod_index = (mod_index + 1) % cycle_length;
//        first = 0;
//    }
//    return start;
    return 0;
}

int main(int argc, char** argv){
    int cycle_length = 0;
    int wheel_length = 0;
    printf("Calculating Cycle . . . \n");
    int* cycle = get_cycle(&cycle_length, &wheel_length);
    printf("Checking %f percent of all numbers\n", 100 * (float)cycle_length / wheel_length);
    printf("Calculating Known Primes . . . \n");
    calculate_known_primes(cycle, cycle_length);
    unsigned long* full_wheel = (unsigned long*)malloc(cycle_length * sizeof(unsigned long));
    full_wheel[0] = 0;
    for (int i = 1; i < cycle_length; i++){
        full_wheel[i] = full_wheel[i - 1] + cycle[i - 1];
    }

    unsigned long* prime_chunk = (unsigned long*)malloc(CHUNK_SIZE * sizeof(unsigned long));
    unsigned int* common_gaps = (unsigned int*)malloc(CHUNK_SIZE * sizeof(unsigned int));
    unsigned int* frequencies = (unsigned int*)malloc(CHUNK_SIZE * sizeof(unsigned int));
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
    printf("Starting Prime Generation . . . \n");
    generate_primes(start, common_gaps, frequencies, &prime_chunk, &chunk_index, &num_chunks, full_wheel, cycle, cycle_length, wheel_length);

}