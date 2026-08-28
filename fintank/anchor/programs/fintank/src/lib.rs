#![allow(clippy::result_large_err)]

use anchor_lang::prelude::*;

declare_id!("Count3AcZucFDPSFBAeHkQ6AvttieKUkyJ8HiQGhQwe");

// Anchor programs always use 8 bits for the discriminator
pub const ANCHOR_DISCRIMINATOR_SIZE: usize = 8;

#[program]
pub mod fintank {
    use super::*;

}


#[account]  
#[derive(InitSpace)]
pub struct JounralEntryState {
    pub journal_id: u64,
    pub owner: Pubkey,
    #[max_len(280)]
    pub title: String,
    pub created_at: u64,
    #[max_len(2000)]
    pub body: String,
}
